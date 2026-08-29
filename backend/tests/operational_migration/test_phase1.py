import csv
import io
import json
from datetime import datetime, timezone

import pytest

from app.operational_migration.phase1 import (
    JOB_HEADERS,
    OperationalPhase1Manifest,
    reviewed_output,
    select_stage,
    stage_records,
    transform_phase1,
)


def source(*, address: str = "10 Main St Testville FL 32000") -> bytes:
    row = {field: "" for field in JOB_HEADERS}
    row.update(
        {
            "Invoice": "1001",
            "HCP Id": "job-1",
            "Date": "2024-03-21 09:30",
            "Customer": "Test Customer",
            "First Name": "Test",
            "Last Name": "Customer",
            "Email": "test@example.test",
            "Address": address,
            "Description": "Leak diagnostic",
            "Employee": "Legacy Employee",
            "Job Status": "DONE",
            "Finished": "2024-03-21 11:15am",
        }
    )
    target = io.StringIO(newline="")
    writer = csv.DictWriter(target, fieldnames=JOB_HEADERS)
    writer.writeheader()
    writer.writerow(row)
    return target.getvalue().encode()


def customer_inputs() -> tuple[bytes, bytes]:
    reviewed = {
        "review_sha256": "a" * 64,
        "aggregates": [
            {
                "source_identity": "customer-1",
                "customer_json": json.dumps(
                    {"display_name": "Test Customer", "legal_name": None}
                ),
                "contact_json": json.dumps(
                    {
                        "first_name": "Test",
                        "last_name": "Customer",
                        "email": "test@example.test",
                        "mobile_phone": None,
                        "office_phone": None,
                    }
                ),
                "service_location_json": [
                    json.dumps(
                        {
                            "address": "10 Main St",
                            "address_line_2": None,
                            "city": "Testville",
                            "state": "FL",
                            "postal_code": "32000",
                        }
                    )
                ],
            }
        ],
    }
    manifest = {
        "reviewed_output_sha256": "a" * 64,
        "manifest_sha256": "b" * 64,
        "ordered_source_identities": ["customer-1"],
    }
    return json.dumps(reviewed).encode(), json.dumps(manifest).encode()


def test_phase1_review_and_manifest_are_deterministic_and_cumulative() -> None:
    customer_reviewed, customer_manifest = customer_inputs()
    first = transform_phase1(
        source_bytes=source(),
        reviewed_customer_bytes=customer_reviewed,
        customer_manifest_bytes=customer_manifest,
    )
    second = transform_phase1(
        source_bytes=source(),
        reviewed_customer_bytes=customer_reviewed,
        customer_manifest_bytes=customer_manifest,
    )

    assert first == second
    assert len(first.jobs) == len(first.appointments) == 1
    assert first.jobs[0].status == "draft"
    assert first.jobs[0].source_service_location_id == (
        "customer-1::service-location::1"
    )
    assert first.appointments[0].arrival_window_start_at is None
    assert first.jobs[0].external_metadata is not None
    assert first.jobs[0].external_metadata["source_status"] == "DONE"

    reviewed = reviewed_output(first)
    stage = select_stage(
        reviewed,
        stage_identifier="phase1-full",
        limit=None,
        prior=None,
        generated_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
    )
    loaded = OperationalPhase1Manifest.model_validate_json(stage.model_dump_json())
    jobs, appointments = stage_records(reviewed, loaded)

    assert jobs == first.jobs
    assert appointments == first.appointments
    assert loaded.expected_business_events == 2


def test_phase1_retains_rows_without_exact_migrated_location() -> None:
    customer_reviewed, customer_manifest = customer_inputs()
    result = transform_phase1(
        source_bytes=source(address="11 Different St Testville FL 32000"),
        reviewed_customer_bytes=customer_reviewed,
        customer_manifest_bytes=customer_manifest,
    )

    assert result.jobs == ()
    assert result.appointments == ()
    assert result.dispositions[0].category == "service_location_not_migrated"


def test_phase1_rejects_unknown_source_layout() -> None:
    customer_reviewed, customer_manifest = customer_inputs()

    with pytest.raises(ValueError, match="unsupported Housecall Pro Job export layout"):
        transform_phase1(
            source_bytes=b"unknown,column\nvalue,value\n",
            reviewed_customer_bytes=customer_reviewed,
            customer_manifest_bytes=customer_manifest,
        )
