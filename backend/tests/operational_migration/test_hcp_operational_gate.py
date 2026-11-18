from pathlib import Path

import pytest
from app.operational_migration.hcp_operational_gate import (
    require_private_file,
    required_operational_holds,
    technician_dispositions,
)


def _appointment(source_id: str, technician_id: str, end: str | None) -> dict:
    payload = {"dispatched_employees_ids": [technician_id]}
    if end is not None:
        payload["end_time"] = end
    return {
        "domain": "appointment",
        "source_id": source_id,
        "payload": payload,
    }


def test_technician_disposition_uses_exact_identity_and_holds_conflicts() -> None:
    provider = {
        "acquired_at": "2026-11-10T12:00:00Z",
        "records": [
            _appointment("a-current", "pro_current", "2026-11-09T12:00:00Z"),
            _appointment("a-former", "pro_former", "2026-11-09T12:00:00Z"),
            _appointment("a-history", "pro_history", "2026-11-09T12:00:00Z"),
            _appointment("a-stale", "pro_stale_active", "2026-11-09T12:00:00Z"),
            _appointment("a-future", "pro_future_unknown", "2026-11-11T12:00:00Z"),
        ],
    }
    authority = {
        "records": [
            {
                "provider_employee_id": "pro_former",
                "employment_status": "TERMINATED",
            },
            {
                "provider_employee_id": "pro_stale_active",
                "employment_status": "ACTIVE",
            },
        ]
    }

    packet = technician_dispositions(
        provider=provider,
        current_employees=({"id": "pro_current"},),
        workforce_authority=authority,
    )

    by_id = {row["source_technician_id"]: row for row in packet["records"]}
    assert by_id["pro_current"]["disposition"] == "CURRENT_EMPLOYEE"
    assert by_id["pro_former"]["disposition"] == "FORMER_EMPLOYEE"
    assert by_id["pro_history"]["disposition"] == "PROVIDER_HISTORICAL_IDENTITY"
    assert by_id["pro_stale_active"]["disposition"] == "UNRESOLVED_HOLD"
    assert by_id["pro_future_unknown"]["disposition"] == "UNRESOLVED_HOLD"
    assert packet["referenced_identity_count"] == 5
    assert packet["absent_from_current_employee_count"] == 4


def test_technician_disposition_is_deterministic() -> None:
    provider = {
        "acquired_at": "2026-11-10T12:00:00Z",
        "records": [
            _appointment("b", "pro_b", "2026-11-09T12:00:00Z"),
            _appointment("a", "pro_a", "2026-11-09T12:00:00Z"),
        ],
    }

    first = technician_dispositions(
        provider=provider,
        current_employees=(),
        workforce_authority={"records": []},
    )
    second = technician_dispositions(
        provider={**provider, "records": list(reversed(provider["records"]))},
        current_employees=(),
        workforce_authority={"records": []},
    )

    assert first == second


def test_required_operational_holds_include_final_policy_corrections() -> None:
    classifications = [
        {
            "domain": "job",
            "source_id": f"held-job-{index}",
            "disposition": "HOLD",
            "reason": "sealed gate hold",
        }
        for index in range(22)
    ] + [
        {
            "domain": "appointment",
            "source_id": f"held-appointment-{index}",
            "disposition": "HOLD",
            "reason": "sealed gate hold",
        }
        for index in range(17)
    ] + [
        {
            "domain": "service_location",
            "source_id": f"held-location-{index}",
            "disposition": "HOLD",
            "reason": "sealed gate hold",
        }
        for index in range(4)
    ]
    provider_keys = [
        (row["domain"], row["source_id"]) for row in classifications
    ] + [
        ("job", "omitted-job"),
        ("appointment", "omitted-appointment"),
        ("appointment", "unassigned-appointment"),
    ]
    provider = {
        "records": [
            {"domain": domain, "source_id": source_id}
            for domain, source_id in provider_keys
        ]
    }
    policy = {
        "resolved_original_gate_omissions": [
            {"domain": "job", "source_id": "omitted-job"},
            {"domain": "appointment", "source_id": "omitted-appointment"},
        ],
        "held_quarantined": {
            "unassigned_appointment": {"source_id": "unassigned-appointment"}
        },
    }

    holds = required_operational_holds(
        gate={"classifications": classifications},
        provider=provider,
        final_policy=policy,
    )

    assert len(holds) == 46
    assert ("job", "omitted-job") in holds
    assert ("appointment", "omitted-appointment") in holds
    assert ("appointment", "unassigned-appointment") in holds


def test_private_evidence_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text("{}")
    target.chmod(0o600)
    link = tmp_path / "link.json"
    link.symlink_to(target)

    with pytest.raises(ValueError, match="sealed evidence file is missing"):
        require_private_file(link)
