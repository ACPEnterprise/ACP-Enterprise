import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.operational_migration.phase2 import (
    ReviewedFinancialOutput,
    reviewed_output,
    select_stage,
    stage_records,
    transform_phase2,
)


def _phase1(source: bytes, job_ids: list[str]) -> bytes:
    payload = {
        "review_version": "operational-migration-phase1-review/v1",
        "source_system": "housecall_pro",
        "export_version": "housecall_pro_job_export_20240321_v1",
        "transformation_version": "operational-phase1-hcp/v1",
        "source_sha256": __import__("hashlib").sha256(source).hexdigest(),
        "customer_review_sha256": "1" * 64,
        "customer_manifest_sha256": "2" * 64,
        "transformation_sha256": "3" * 64,
        "source_count": len(job_ids),
        "eligible_job_count": len(job_ids),
        "eligible_appointment_count": 0,
        "jobs": [
            {
                "source_id": value,
                "source_customer_id": "customer-1",
                "source_service_location_id": "location-1",
                "status": "draft",
                "assigned_technician_source_ids": [],
            }
            for value in job_ids
        ],
        "appointments": [],
        "dispositions": [],
        "disposition_counts": {},
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    payload["review_sha256"] = (
        __import__("hashlib").sha256(canonical.encode()).hexdigest()
    )
    return json.dumps(payload).encode()


def _source(path: Path, rows: list[dict[str, str]]) -> bytes:
    headers = [
        "Invoice",
        "HCP Id",
        "Line Items",
        "Amount",
        "Subtotal",
        "Payment History",
        "Job Status",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    return path.read_bytes()


def test_phase2_preserves_source_money_and_builds_cumulative_manifest(
    tmp_path: Path,
) -> None:
    source = _source(
        tmp_path / "source.csv",
        [
            {
                "Invoice": '="100"',
                "HCP Id": "job-1",
                "Line Items": "Line Items\nDiagnostic - $125.50\n",
                "Amount": "$125.50",
                "Subtotal": "$125.50",
                "Payment History": "2024-01-02 03:04pm - $125.50 - Check - ",
                "Job Status": "DONE",
            },
            {
                "Invoice": '="200"',
                "HCP Id": "job-2",
                "Line Items": "Line Items\nRepair - $40.00\nPart - $10.25\n",
                "Amount": "$50.25",
                "Subtotal": "$50.25",
                "Payment History": "",
                "Job Status": "SCHEDULED",
            },
        ],
    )
    phase1 = _phase1(source, ["job-1", "job-2"])
    review = reviewed_output(
        transform_phase2(source_bytes=source, phase1_review_bytes=phase1)
    )
    assert review.eligible_invoice_count == 2
    assert review.eligible_invoice_line_item_count == 3
    assert review.eligible_payment_count == 1
    assert review.invoice_records()[0].tax_amount == 0
    assert sum(
        item.total_amount for item in review.invoice_records()[0].line_items
    ) in {
        __import__("decimal").Decimal("125.50"),
        __import__("decimal").Decimal("50.25"),
    }
    stage1 = select_stage(
        review,
        stage_identifier="financial-1",
        limit=1,
        prior=None,
        generated_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
    )
    full = select_stage(
        review,
        stage_identifier="financial-full",
        limit=None,
        prior=stage1,
        generated_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
    )
    assert (
        full.ordered_invoice_source_identities[:1]
        == stage1.ordered_invoice_source_identities
    )
    assert full.expected_invoices == 2
    assert full.expected_invoice_line_items == 3
    invoices, payments = stage_records(review, full)
    assert len(invoices) == 2
    assert len(payments) == 1
    ReviewedFinancialOutput.model_validate(review.model_dump())


@pytest.mark.parametrize(
    ("change", "category"),
    [
        ({"Amount": "$12.00", "Subtotal": "$10.00"}, "monetary_imbalance"),
        ({"Line Items": ""}, "incomplete_financial_detail"),
        (
            {
                "Payment History": "2024-01-02 03:04pm - ($10.00) - Credit Card Refund - "
            },
            "unsupported_lifecycle",
        ),
    ],
)
def test_phase2_separates_unsafe_financial_records(
    tmp_path: Path, change: dict[str, str], category: str
) -> None:
    row = {
        "Invoice": '="100"',
        "HCP Id": "job-1",
        "Line Items": "Line Items\nDiagnostic - $10.00\n",
        "Amount": "$10.00",
        "Subtotal": "$10.00",
        "Payment History": "",
        "Job Status": "DONE",
    }
    row.update(change)
    source = _source(tmp_path / "source.csv", [row])
    review = reviewed_output(
        transform_phase2(
            source_bytes=source, phase1_review_bytes=_phase1(source, ["job-1"])
        )
    )
    assert review.eligible_invoice_count == 0
    assert review.disposition_counts == {category: 1}
