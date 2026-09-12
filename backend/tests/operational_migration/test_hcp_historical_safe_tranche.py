import hashlib
import json
from pathlib import Path

import pytest
from app.operational_migration.hcp_historical_safe_tranche import (
    ACCEPTANCE_CONTRACT,
    NATIVE_BINDING_CONTRACT,
    OVERLAY_CONTRACT,
    build_historical_tranche,
)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _write_inputs(tmp_path: Path) -> tuple[Path, Path]:
    company, branch = "company-1", "branch-1"
    overlay_records: list[dict[str, object]] = []
    plan_records: list[dict[str, object]] = []

    def add(
        domain: str,
        source_id: str,
        classification: str,
        assertion: str,
        parents: list[str],
        payload: dict[str, object],
    ) -> None:
        source_digest = hashlib.sha256(source_id.encode()).hexdigest()
        parent_values = [
            {"domain": item.split(":", 1)[0], "source_id": item.split(":", 1)[1]}
            for item in parents
        ]
        overlay_records.append(
            {
                "domain": domain,
                "source_id": source_id,
                "assertion": assertion,
                "source_digest": source_digest,
                "prior_source_digest": "f" * 64 if assertion == "update" else None,
                "acquired_at": "2026-09-12T16:49:00+00:00",
                "parent_keys": parent_values,
                "payload": payload,
            }
        )
        plan_records.append(
            {
                "domain": domain,
                "source_id": source_id,
                "assertion": assertion,
                "classification": classification,
                "reason": "accepted",
                "source_digest": source_digest,
                "parent_keys": parents,
            }
        )

    for index in range(51):
        add("customer", f"c{index}", "SAFE_HISTORICAL", "create", [], {})
    for index in range(37):
        add(
            "service_location",
            f"l{index}",
            "SAFE_HISTORICAL",
            "create",
            ["customer:c0"],
            {},
        )
    for index in range(27):
        add(
            "job",
            f"j{index}",
            "SAFE_HISTORICAL",
            "create",
            ["customer:c0", "service_location:l0"],
            {"work_status": "scheduled", "work_timestamps": {}},
        )
    for index in range(34):
        add(
            "appointment",
            f"a{index}",
            "SAFE_HISTORICAL",
            "create",
            ["job:j0"],
            {"start_time": "2025-01-01T12:00:00Z", "end_time": "2025-01-01T13:00:00Z"},
        )
    for index in range(15):
        add("customer", f"cu{index}", "SAFE_UPDATE", "update", [], {})
    for index in range(22):
        add(
            "job",
            f"ju{index}",
            "SAFE_UPDATE",
            "update",
            ["customer:c0", "service_location:l0"],
            {"work_status": "scheduled", "work_timestamps": {}},
        )

    overlay = {
        "contract": OVERLAY_CONTRACT,
        "digest": "a" * 64,
        "company_id": company,
        "branch_id": branch,
        "records": overlay_records,
    }
    overlay_path = tmp_path / "overlay.json"
    overlay_path.write_text(json.dumps(overlay), encoding="utf-8")
    plan = {
        "contract": ACCEPTANCE_CONTRACT,
        "overlay_manifest_digest": overlay["digest"],
        "overlay_file_sha256": hashlib.sha256(overlay_path.read_bytes()).hexdigest(),
        "records": plan_records,
    }
    plan["digest"] = _digest(plan)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    return overlay_path, plan_path


def test_builds_only_accepted_149_37_and_holds_unbound_updates(tmp_path: Path) -> None:
    overlay, plan = _write_inputs(tmp_path)
    packet = build_historical_tranche(
        overlay_path=overlay,
        acceptance_plan_path=plan,
        protected_authority="1" * 40,
    )
    packet.verify()
    assert len(packet.records) == 186
    assert (
        sum("ADMIT" in key and value for key, value in packet.readiness_counts.items())
        == 149
    )
    assert packet.readiness_counts["customer:HOLD"] == 15
    assert packet.readiness_counts["job:HOLD"] == 22
    assert packet.execution_allowed is False
    assert "SAFE_UPDATE_NATIVE_BINDINGS_REQUIRED" in packet.execution_blockers


def test_rejects_acceptance_plan_tampering(tmp_path: Path) -> None:
    overlay, plan_path = _write_inputs(tmp_path)
    plan = json.loads(plan_path.read_bytes())
    plan["records"][0]["source_id"] = "changed"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(ValueError, match="acceptance plan digest mismatch"):
        build_historical_tranche(
            overlay_path=overlay,
            acceptance_plan_path=plan_path,
            protected_authority="1" * 40,
        )


def test_rejects_conflicting_cross_scope_binding(tmp_path: Path) -> None:
    overlay, plan = _write_inputs(tmp_path)
    bindings = tmp_path / "bindings.json"
    evidence = {
        "contract": NATIVE_BINDING_CONTRACT,
        "mutation_authority": "none",
        "bindings": [
            {
                "domain": "customer",
                "source_id": "cu0",
                "native_id": "native-1",
                "company_id": "other-company",
                "branch_id": "branch-1",
                "source_digest": "f" * 64,
            }
        ],
    }
    evidence["digest"] = _digest(evidence)
    bindings.write_text(json.dumps(evidence), encoding="utf-8")
    with pytest.raises(ValueError, match="conflicting native binding evidence"):
        build_historical_tranche(
            overlay_path=overlay,
            acceptance_plan_path=plan,
            protected_authority="1" * 40,
            native_bindings_path=bindings,
        )
