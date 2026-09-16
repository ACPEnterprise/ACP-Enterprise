import hashlib
import json
from pathlib import Path

import pytest
from app.operational_migration.hcp_job_appointment_history_readiness import (
    build_readiness,
)


def _write(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _authority(root: Path) -> None:
    jobs = {
        "jobs": [
            {
                "id": "job_complete",
                "customer": {"id": "cus_1"},
                "address": {"id": "adr_1"},
                "work_status": "complete rated",
                "assigned_employees": [{"id": "pro_1"}],
            },
            {
                "id": "job_location_gap",
                "customer": {"id": "cus_2"},
                "address": None,
                "work_status": "complete unrated",
                "assigned_employees": [],
            },
        ]
    }
    jobs_sha = _write(root / "raw/jobs/page-0001.json", jobs)
    collection = {
        "acquisition_completed_at": "2026-08-27T00:00:00+00:00",
        "collections": {
            "jobs": {
                "page_sha256s": [jobs_sha],
                "record_count": 2,
            }
        },
    }
    _write(root / "collection-manifest.json", collection)
    acquisition = {"manifest_sha256": "a" * 64}
    _write(root / "acquisition-package-manifest.json", acquisition)

    complete_hash = hashlib.sha256(b"job_complete").hexdigest()
    gap_hash = hashlib.sha256(b"job_location_gap").hexdigest()
    response_sha = _write(
        root / f"raw/job-appointments-2023-plus/{complete_hash}.json",
        {
            "appointments": [
                {
                    "id": "appt_1",
                    "start_time": "2026-01-01T12:00:00Z",
                    "end_time": "2026-01-01T13:00:00Z",
                    "arrival_window_minutes": 60,
                    "anytime": False,
                    "dispatched_employees_ids": ["pro_1"],
                }
            ]
        },
    )
    relationships = {
        "appointment_record_count": 1,
        "artifacts": [
            {
                "job_identity_sha256": complete_hash,
                "http_status": 200,
                "response_sha256": response_sha,
                "effective_retry_sha256": None,
            },
            {
                "job_identity_sha256": gap_hash,
                "http_status": 400,
                "response_sha256": "b" * 64,
                "effective_retry_sha256": None,
            },
        ],
    }
    _write(root / "relationship-appointments-manifest.json", relationships)


def test_classifies_exact_source_graph_without_native_or_employee_inference(
    tmp_path: Path,
) -> None:
    _authority(tmp_path)
    first = build_readiness(source_root=tmp_path)
    second = build_readiness(source_root=tmp_path)

    assert first == second
    assert first["counts"] == {
        "jobs": {
            "total": 2,
            "LOCATION_SOURCE_MISSING": 1,
            "SOURCE_GRAPH_READY": 1,
        },
        "appointments": {"total": 1, "SOURCE_GRAPH_READY": 1},
        "appointment_relationships": {
            "PROVIDER_RELATIONSHIP_ERROR": 1,
            "RELATIONSHIP_WITH_APPOINTMENTS": 1,
        },
    }
    appointment = first["records"]["appointments"][0]
    assert appointment["source_technician_ids"] == ["pro_1"]
    assert appointment["technician_authority"] == "SOURCE_BACKED_NOT_NATIVE_BOUND"
    assert appointment["native_admission_disposition"] == "BINDING_EVIDENCE_REQUIRED"


def test_rejects_changed_sealed_job_page(tmp_path: Path) -> None:
    _authority(tmp_path)
    page = tmp_path / "raw/jobs/page-0001.json"
    page.write_text(page.read_text() + " ")
    with pytest.raises(ValueError, match="digest mismatch"):
        build_readiness(source_root=tmp_path)
