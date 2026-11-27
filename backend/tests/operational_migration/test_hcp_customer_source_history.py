import hashlib
import json
from pathlib import Path

import pytest
from app.operational_migration.hcp_customer_source_history import (
    HcpCustomerSourceHistoryError,
    project_customer_source_history,
    search_customer_source_history,
)


def _page(root: Path, family: str, rows: list[dict[str, object]]) -> None:
    target = root / "raw" / family
    target.mkdir(parents=True)
    (target / "page-0001.json").write_text(json.dumps({family: rows}))


def _source(root: Path) -> Path:
    (root / "acquisition-package-manifest.json").write_text(
        json.dumps(
            {
                "contract": "hcp-source-4-acquisition-package/v1",
                "request_methods": ["GET"],
            }
        )
    )
    _page(
        root,
        "customers",
        [
            {
                "id": "customer-1",
                "display_name": "Richard Example",
                "email": "richard@example.test",
                "addresses": [
                    {
                        "id": "location-1",
                        "street": "123 Main St",
                        "city": "Clearwater",
                        "state": "FL",
                        "zip": "33755",
                    }
                ],
            }
        ],
    )
    _page(
        root,
        "estimates",
        [
            {
                "id": "estimate-1",
                "estimate_number": "100",
                "customer": {"id": "customer-1"},
                "work_status": "approved",
                "options": [
                    {"id": "option-1", "name": "Repair", "total_amount": 12500}
                ],
            },
            {
                "id": "estimate-other",
                "customer": {"id": "customer-other"},
                "options": [],
            },
        ],
    )
    _page(
        root,
        "jobs",
        [
            {
                "id": "job-1",
                "customer": {"id": "customer-1"},
                "address": {"id": "location-1"},
            },
            {"id": "job-other", "customer": {"id": "customer-other"}},
        ],
    )
    _page(
        root,
        "invoices",
        [
            {
                "id": "invoice-1",
                "job_id": "job-1",
                "invoice_number": "200",
                "status": "paid",
                "amount": 12500,
                "due_amount": 0,
                "payments": [
                    {
                        "id": "payment-1",
                        "status": "succeeded",
                        "amount": 12500,
                        "payment_method": "imported_from_quickbooks",
                    }
                ],
                "refunds": [
                    {
                        "id": None,
                        "status": "succeeded",
                        "amount": 2500,
                        "refunded_at": "2026-05-20T12:00:00Z",
                        "payment_method": "card",
                    }
                ],
            },
            {"id": "invoice-other", "job_id": "job-other", "payments": []},
        ],
    )
    return root


def test_projects_exact_customer_history_without_accounting_promotion(
    tmp_path: Path,
) -> None:
    result = project_customer_source_history(
        _source(tmp_path), source_customer_id="customer-1"
    )

    assert result["counts"] == {
        "locations": 1,
        "jobs": 1,
        "appointments": 0,
        "estimates": 1,
        "invoices": 1,
        "payments": 1,
        "refunds": 1,
    }
    assert result["locations"][0]["source_id"] == "location-1"
    assert result["jobs"][0]["source_location_id"] == "location-1"
    assert result["accepted_as_acp_accounting"] is False
    assert result["mutation_authority"] == "none"
    assert result["estimates"][0]["source_id"] == "estimate-1"
    payment = result["invoices"][0]["payments"][0]
    assert payment["overlap_disposition"] == (
        "HOLD_FROM_AGGREGATION_PENDING_QBO_RECONCILIATION"
    )
    refund = result["invoices"][0]["refunds"][0]
    assert refund["identity_disposition"] == "SOURCE_BACKED_UNLINKED_REFUND"
    assert refund["aggregation_safe"] is False


def test_rejects_non_read_only_source_package(tmp_path: Path) -> None:
    root = _source(tmp_path)
    (root / "acquisition-package-manifest.json").write_text(
        json.dumps(
            {
                "contract": "hcp-source-4-acquisition-package/v1",
                "request_methods": ["GET", "POST"],
            }
        )
    )

    with pytest.raises(HcpCustomerSourceHistoryError, match="not_read_only"):
        project_customer_source_history(root, source_customer_id="customer-1")


def test_projects_incomplete_job_facts_and_recovered_attachments_as_history(
    tmp_path: Path,
) -> None:
    root = _source(tmp_path)
    details = root / "raw" / "job-details"
    details.mkdir()
    (details / "job-detail-1.json").write_text(
        json.dumps(
            {
                "id": "job-1",
                "description": "Historical leak repair",
                "schedule": {"scheduled_start": "2026-05-20T12:00:00Z"},
                "notes": [{"id": "note-1", "content": "Technician note"}],
                "assigned_employees": [{"id": "employee-1"}],
            }
        )
    )
    appointments = root / "raw" / "appointments"
    appointments.mkdir()
    digest = hashlib.sha256(b"job-1").hexdigest()
    (appointments / f"job-appointments-{digest}-http-200.json").write_text(
        json.dumps(
            {
                "appointments": [
                    {"id": "appointment-1", "start_time": "2026-05-20T12:00:00Z"}
                ]
            }
        )
    )
    attachment_root = tmp_path / "attachments"
    attachment_root.mkdir()
    (attachment_root / "attachment-body.bin").write_bytes(b"image")
    (attachment_root / "attachment-custody-manifest.json").write_text(
        json.dumps(
            {
                "attachments": [
                    {
                        "source_id": "attachment-1",
                        "job_id": "job-1",
                        "file_name": "leak.jpg",
                        "file_type": "image/jpeg",
                        "size_bytes": 5,
                        "content_sha256": hashlib.sha256(b"image").hexdigest(),
                        "artifact": "attachment-body.bin",
                        "status": "RECOVERED",
                    }
                ],
                "conflicts": [],
            }
        )
    )

    result = project_customer_source_history(
        root,
        source_customer_id="customer-1",
        attachment_root=attachment_root,
    )

    job = result["jobs"][0]
    assert job["service_date"] == "2026-05-20T12:00:00Z"
    assert job["description"] == "Historical leak repair"
    assert job["notes"][0]["content"] == "Technician note"
    assert job["assigned_employee_source_ids"] == ["employee-1"]
    assert result["counts"]["appointments"] == 1
    assert job["attachments"][0]["body_available"] is True


def test_searches_historical_customer_and_location_without_native_identity(
    tmp_path: Path,
) -> None:
    root = _source(tmp_path)
    by_name = search_customer_source_history(root, query="richard")
    by_location = search_customer_source_history(root, query="clearwater")
    assert by_name["items"] == by_location["items"]
    assert by_name["items"][0] == {
        "source_customer_id": "customer-1",
        "display_name": "Richard Example",
        "primary_location": "123 Main St, Clearwater, FL, 33755",
        "authority": "HCP_SOURCE_BACKED_HISTORICAL_CUSTOMER",
        "accepted_as_native": False,
    }
    assert by_name["mutation_authority"] == "none"


def test_historical_customer_search_requires_bounded_meaningful_query(
    tmp_path: Path,
) -> None:
    root = _source(tmp_path)
    with pytest.raises(HcpCustomerSourceHistoryError, match="too_short"):
        search_customer_source_history(root, query="r")
    with pytest.raises(HcpCustomerSourceHistoryError, match="limit_invalid"):
        search_customer_source_history(root, query="richard", limit=51)
