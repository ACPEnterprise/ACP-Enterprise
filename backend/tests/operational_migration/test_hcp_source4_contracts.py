import hashlib
import json

import pytest
from app.operational_migration.hcp_source4_contracts import (
    ADDRESS_KEYS,
    APPOINTMENT_COLUMNS,
    CUSTOMER_KEYS,
    EMPLOYEE_KEYS,
    ESTIMATE_COLUMNS,
    INVOICE_COLUMNS,
    JOB_COLUMNS,
    NOTE_COLUMNS,
    PAYMENT_COLUMNS,
    SCHEDULE_KEYS,
)
from app.operational_migration.transformation import (
    ParsedSourceExport,
    housecall_pro_operational_pipeline,
)

DIGEST = "a" * 64


def job() -> dict[str, object]:
    row = {column: None for column in JOB_COLUMNS}
    row.update(
        {
            "id": "job_1",
            "customer": {**dict.fromkeys(CUSTOMER_KEYS), "id": "cus_1"},
            "address": {**dict.fromkeys(ADDRESS_KEYS), "id": "adr_1"},
            "work_status": "scheduled",
            "work_timestamps": {
                "started_at": None,
                "completed_at": None,
                "on_my_way_at": None,
            },
            "schedule": dict.fromkeys(SCHEDULE_KEYS),
            "assigned_employees": [{**dict.fromkeys(EMPLOYEE_KEYS), "id": "pro_1"}],
            "job_fields": {"business_unit": None, "job_type": None},
            "notes": [],
            "description": "synthetic",
            "_source_digest": DIGEST,
            "_owner_disposition": "automatic",
        }
    )
    return row


def appointment() -> dict[str, object]:
    return {
        "id": "appt_1",
        "start_date": None,
        "start_time": "2026-08-27T12:00:00Z",
        "end_time": "2026-08-27T13:00:00Z",
        "anytime": False,
        "arrival_window_minutes": 120,
        "dispatched_employees_ids": ["pro_1"],
        "_source_digest": DIGEST,
        "_source_job_id": "job_1",
        "_source_customer_id": "cus_1",
        "_source_location_id": "adr_1",
        "_job_status": "scheduled",
        "_owner_disposition": "automatic",
    }


def estimate() -> dict[str, object]:
    row = {column: None for column in ESTIMATE_COLUMNS}
    row.update(
        {
            "id": "csr_1",
            "customer": {**dict.fromkeys(CUSTOMER_KEYS), "id": "cus_1"},
            "address": {**dict.fromkeys(ADDRESS_KEYS), "id": "adr_1"},
            "work_timestamps": {
                "started_at": None,
                "completed_at": None,
                "on_my_way_at": None,
            },
            "schedule": dict.fromkeys(SCHEDULE_KEYS),
            "assigned_employees": [],
            "estimate_fields": {"business_unit": None, "job_type": None},
            "options": [
                {
                    "id": "est_1",
                    "name": "synthetic option",
                    "approval_status": "approved",
                    "status": "approved",
                    "total_amount": 10000,
                    "created_at": "2026-08-27T12:00:00Z",
                    "message_from_pro": None,
                    "notes": None,
                    "option_number": "1",
                    "tags": [],
                    "updated_at": "2026-08-27T12:00:00Z",
                }
            ],
            "work_status": "created job from estimate",
            "_source_digest": DIGEST,
            "_source_job_id": "job_1",
            "_selected_option_id": "est_1",
            "_owner_disposition": "authoritative_job_link",
        }
    )
    return row


def invoice() -> dict[str, object]:
    row = {column: None for column in INVOICE_COLUMNS}
    row.update(
        {
            "id": "invoice_1",
            "job_id": "job_1",
            "status": "open",
            "subtotal": 10000,
            "amount": 10700,
            "items": [
                {
                    "id": "invitm_1",
                    "name": "synthetic item",
                    "qty_in_hundredths": 100,
                    "unit_price": 10000,
                    "amount": 10000,
                    "invoiced_amount": 10000,
                    "type": "service",
                    "unit_cost": 0,
                }
            ],
            "payments": [],
            "refunds": [],
            "discounts": [],
            "taxes": [],
            "invoice_date": "2026-08-27T12:00:00Z",
            "_source_digest": DIGEST,
            "_owner_disposition": "financial_assertion_hold",
        }
    )
    return row


def payment() -> dict[str, object]:
    return {
        "id": "invpay_1",
        "amount": 10000,
        "category": "payment",
        "note": None,
        "paid_at": "2026-08-27T12:00:00Z",
        "payment_method": "cash",
        "status": "succeeded",
        "surcharge_fee_amount": 0,
        "_source_digest": DIGEST,
        "_source_invoice_id": "invoice_1",
        "_owner_disposition": "payment_assertion_only",
    }


@pytest.mark.parametrize(
    ("entity", "version", "columns", "row"),
    (
        ("job", "hcp_source4_jobs_api_v1", JOB_COLUMNS, job()),
        (
            "appointment",
            "hcp_source4_job_appointments_api_v1",
            APPOINTMENT_COLUMNS,
            appointment(),
        ),
        (
            "estimate",
            "hcp_source4_estimate_options_api_v1",
            ESTIMATE_COLUMNS,
            estimate(),
        ),
        ("invoice", "hcp_source4_invoices_api_v1", INVOICE_COLUMNS, invoice()),
        (
            "payment",
            "hcp_source4_invoice_payments_api_v1",
            PAYMENT_COLUMNS,
            payment(),
        ),
    ),
)
def test_registered_source4_layouts_are_deterministic(
    entity: str, version: str, columns: tuple[str, ...], row: dict[str, object]
) -> None:
    raw = json.dumps(row, sort_keys=True).encode()
    source = ParsedSourceExport.from_source_bytes(
        entity=entity,  # type: ignore[arg-type]
        version=version,
        columns=columns,
        rows=(row,),
        source_bytes=raw,
    )
    first = housecall_pro_operational_pipeline().transform(
        source, expected_source_sha256=hashlib.sha256(raw).hexdigest()
    )
    second = housecall_pro_operational_pipeline().transform(
        source, expected_source_sha256=source.source_sha256
    )
    assert first.accepted == 1
    assert first.transformation_sha256 == second.transformation_sha256
    assert first.records[0].external_metadata["source_digest"] == DIGEST  # type: ignore[union-attr]


def test_changed_and_unknown_layouts_remain_fail_closed() -> None:
    row = job()
    columns = JOB_COLUMNS[:-1]
    source = ParsedSourceExport.from_source_bytes(
        entity="job",
        version="hcp_source4_jobs_api_v1",
        columns=columns,
        rows=({key: row[key] for key in columns},),
        source_bytes=b"changed",
    )
    changed = housecall_pro_operational_pipeline().transform(
        source, expected_source_sha256=source.source_sha256
    )
    unknown = ParsedSourceExport.from_source_bytes(
        entity="job",
        version="hcp_source4_jobs_api_v2",
        columns=JOB_COLUMNS,
        rows=(row,),
        source_bytes=b"unknown",
    )
    rejected = housecall_pro_operational_pipeline().transform(
        unknown, expected_source_sha256=unknown.source_sha256
    )
    assert changed.rejections[0].code == "changed_layout"
    assert rejected.rejections[0].code == "unsupported_export_version"


def test_note_layout_preserves_unavailable_timestamp_as_rejection() -> None:
    row = {
        "id": "nte_1",
        "content": "synthetic note",
        "_source_digest": DIGEST,
        "_source_job_id": "job_1",
        "_occurred_at": None,
        "_owner_disposition": "partial_note_provenance",
    }
    source = ParsedSourceExport.from_source_bytes(
        entity="note",
        version="hcp_source4_job_notes_partial_api_v1",
        columns=NOTE_COLUMNS,
        rows=(row,),
        source_bytes=b"note",
    )
    report = housecall_pro_operational_pipeline().transform(
        source, expected_source_sha256=source.source_sha256
    )
    assert report.accepted == 0
    assert report.rejections[0].code == "note_timestamp_unavailable"
