import json
from pathlib import Path

import pytest
from app.operational_migration.hcp_estimate_history_readiness import (
    build_estimate_history_readiness,
    canonical_bytes,
)


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))


def _authority(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    source = tmp_path / "source" / "raw"
    estimates = []
    jobs = []
    crosswalk = []
    for index in range(1307):
        estimate_id = f"csr_{index:04d}"
        customer_id = f"cus_{index:04d}"
        option_id = f"est_{index:04d}"
        estimates.append(
            {
                "id": estimate_id,
                "customer": {"id": customer_id},
                "address": {"id": f"adr_{index:04d}"} if index < 1261 else None,
                "work_status": "complete rated",
                "options": [{"id": option_id}],
            }
        )
        if index < 331:
            jobs.append(
                {
                    "id": f"job_{index:04d}",
                    "customer": {"id": customer_id},
                    "address": {"id": f"adr_{index:04d}"},
                    "original_estimate_uuids": [option_id],
                }
            )
        elif index < 387:
            for suffix in ("a", "b"):
                jobs.append(
                    {
                        "id": f"job_{index:04d}{suffix}",
                        "customer": {"id": customer_id},
                        "address": {"id": f"adr_{index:04d}"},
                        "original_estimate_uuids": [option_id],
                    }
                )
        crosswalk.append(
            {
                "native_estimate_id": estimate_id,
                "source_digest": f"digest-{index}",
                "history_layer": "enterprise_analytical_history",
                "control_classification": "AVAILABLE",
            }
        )
    _write(source / "estimates" / "page-0001.json", {"estimates": estimates})
    _write(source / "jobs" / "page-0001.json", {"jobs": jobs})
    acquisition = tmp_path / "source" / "acquisition-package-manifest.json"
    control = tmp_path / "source" / "reconciliation" / "estimate-crosswalk.json"
    _write(acquisition, {"contract": "source"})
    _write(control, crosswalk)

    refresh = tmp_path / "refresh"
    refreshed = estimates + [
        {
            "id": f"csr_delta_{index:02d}",
            "customer": {"id": f"cus_delta_{index:02d}"},
            "address": None,
            "work_status": "needs scheduling",
            "options": [{"id": f"est_delta_{index:02d}"}],
        }
        for index in range(15)
    ]
    _write(refresh / "estimates-page-0001.json", {"estimates": refreshed})
    refresh_manifest = refresh / "current-refresh-manifest.json"
    _write(refresh_manifest, {"contract": "refresh"})
    return source, acquisition, control, refresh, refresh_manifest


def test_builds_complete_deterministic_readiness_packet(tmp_path: Path) -> None:
    source, acquisition, control, refresh, refresh_manifest = _authority(tmp_path)

    first = build_estimate_history_readiness(
        source_root=source,
        acquisition_manifest_path=acquisition,
        control_crosswalk_path=control,
        refresh_root=refresh,
        refresh_manifest_path=refresh_manifest,
    )
    second = build_estimate_history_readiness(
        source_root=source,
        acquisition_manifest_path=acquisition,
        control_crosswalk_path=control,
        refresh_root=refresh,
        refresh_manifest_path=refresh_manifest,
    )

    assert canonical_bytes(first) == canonical_bytes(second)
    assert first["counts"] == {
        "sealed_estimates": 1307,
        "source_customer_identity_present": 1307,
        "source_location_identity_present": 1261,
        "relationship_classifications": {
            "CUSTOMER_ONLY": 920,
            "MULTIPLE_AUTHORITATIVE_JOBS": 56,
            "SINGLE_AUTHORITATIVE_JOB": 331,
        },
        "candidate_dispositions": {
            "CUSTOMER_ONLY_HISTORY": 920,
            "OWNER_DECISION_REQUIRED": 56,
            "SAFE_ADMIT_BINDING_DEPENDENT": 331,
        },
        "native_safe_admit_proven": 0,
    }
    assert first["refresh_delta"]["added_count"] == 15
    assert first["refresh_delta"]["classification"] == "OUTSIDE_SEALED_AUTHORITY"
    assert first["guardrails"]["mutation_authorized"] is False
    assert all("native_id" not in record for record in first["records"])


def test_rejects_fabricated_job_customer_relationship(tmp_path: Path) -> None:
    source, acquisition, control, _, _ = _authority(tmp_path)
    job_path = source / "jobs" / "page-0001.json"
    payload = json.loads(job_path.read_bytes())
    payload["jobs"][0]["customer"]["id"] = "cus_conflict"
    _write(job_path, payload)

    with pytest.raises(ValueError, match="Customer graph conflicts"):
        build_estimate_history_readiness(
            source_root=source,
            acquisition_manifest_path=acquisition,
            control_crosswalk_path=control,
        )


def test_rejects_missing_sealed_control_record(tmp_path: Path) -> None:
    source, acquisition, control, _, _ = _authority(tmp_path)
    rows = json.loads(control.read_bytes())
    _write(control, rows[:-1])

    with pytest.raises(ValueError, match="does not cover"):
        build_estimate_history_readiness(
            source_root=source,
            acquisition_manifest_path=acquisition,
            control_crosswalk_path=control,
        )
