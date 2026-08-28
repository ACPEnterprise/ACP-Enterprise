import copy
import hashlib
import json
from importlib.resources import files
from pathlib import Path

import pytest

from app.engineering_control.scheduler.bank import (
    MilestoneBankIngestionError,
    bank_fingerprint,
    ingest_milestone_bank,
    load_milestone_bank,
    load_milestone_bank_projection,
    project_milestone_bank,
)

REPOSITORY = Path(__file__).resolve().parents[3]
BANK_PATH = (
    REPOSITORY
    / "backend/app/engineering_control/scheduler/milestone-bank.v2.json"
)
MANIFEST_PATH = (
    REPOSITORY
    / "backend/app/engineering_control/scheduler/scheduler-manifest.v1.json"
)


def raw_bank() -> dict[str, object]:
    return json.loads(BANK_PATH.read_text(encoding="utf-8"))


def resign(raw: dict[str, object]) -> dict[str, object]:
    raw["fingerprint"] = bank_fingerprint(
        {key: value for key, value in raw.items() if key != "fingerprint"}
    )
    return raw


def milestones(raw: dict[str, object]) -> list[dict[str, object]]:
    value = raw["milestones"]
    assert isinstance(value, list)
    return value


def milestone(raw: dict[str, object], milestone_id: str) -> dict[str, object]:
    return next(item for item in milestones(raw) if item["milestone_id"] == milestone_id)


def test_valid_bank_ingestion_and_deterministic_projection() -> None:
    bank = load_milestone_bank()
    first = project_milestone_bank(bank)
    second = load_milestone_bank_projection()
    assert first == second
    assert len(first.milestones) == 250
    assert first.ready_milestone_ids == ("BANK.PUR.001", "BANK.BEA.001")
    assert first.milestones == tuple(
        sorted(
            first.milestones,
            key=lambda item: (
                {"P0": 0, "P1": 1, "P2": 2, "P3": 3}[item.priority],
                item.milestone_id,
            ),
        )
    )


def test_unsupported_schema_and_fingerprint_mismatch_fail_closed() -> None:
    unsupported = raw_bank()
    unsupported["schema_version"] = "3.0"
    with pytest.raises(MilestoneBankIngestionError, match="schema or readiness"):
        ingest_milestone_bank(resign(unsupported))

    mismatch = raw_bank()
    mismatch["purpose"] = "tampered"
    with pytest.raises(MilestoneBankIngestionError, match="fingerprint mismatch"):
        ingest_milestone_bank(mismatch)


def test_duplicate_missing_and_nonreciprocal_edges_fail_closed() -> None:
    duplicate = raw_bank()
    milestones(duplicate)[1]["milestone_id"] = milestones(duplicate)[0]["milestone_id"]
    with pytest.raises(MilestoneBankIngestionError, match="duplicate milestone ID"):
        ingest_milestone_bank(resign(duplicate))

    missing = raw_bank()
    missing_dependencies = milestone(missing, "BANK.PUR.002")["dependencies"]
    assert isinstance(missing_dependencies, list)
    missing_dependencies.append("BANK.UNKNOWN.999")
    with pytest.raises(MilestoneBankIngestionError, match="missing dependency"):
        ingest_milestone_bank(resign(missing))

    nonreciprocal = raw_bank()
    milestone(nonreciprocal, "BANK.PUR.001")["successor_ids"] = []
    with pytest.raises(MilestoneBankIngestionError, match="nonreciprocal dependency"):
        ingest_milestone_bank(resign(nonreciprocal))


def test_cycle_and_contradictory_readiness_fail_closed() -> None:
    cycle = raw_bank()
    first = milestone(cycle, "BANK.PUR.001")
    last = milestone(cycle, "BANK.PUR.014")
    first["dependencies"] = ["BANK.PUR.014"]
    last_successors = last["successor_ids"]
    assert isinstance(last_successors, list)
    last_successors.append("BANK.PUR.001")
    first["readiness_state"] = "BLOCKED_DEPENDENCY"
    with pytest.raises(MilestoneBankIngestionError, match="dependency cycle"):
        ingest_milestone_bank(resign(cycle))

    contradictory = raw_bank()
    ready = milestone(contradictory, "BANK.PUR.001")
    ready["owner_decision_required"] = True
    with pytest.raises(MilestoneBankIngestionError, match="unresolved gate"):
        ingest_milestone_bank(resign(contradictory))


def test_gate_ownership_collision_and_risk_metadata_are_preserved() -> None:
    projection = load_milestone_bank_projection()
    by_id = {item.milestone_id: item for item in projection.milestones}

    owner = by_id["BANK.FIELD.001"]
    assert owner.ownership_state == "ACTIVE_OWNED"
    assert owner.owner_decision_required
    assert "ownership:ACTIVE_OWNED" in owner.blocked_reasons

    finance = by_id["BANK.ACC.001"]
    assert finance.finance_decision_required
    assert "finance_decision_required" in finance.blocked_reasons

    external = by_id["BANK.MIG.001"]
    assert external.external_gate != "none"
    assert any(reason.startswith("external_gate:") for reason in external.blocked_reasons)

    purchasing = by_id["BANK.PUR.001"]
    assert purchasing.collision_domain == "purchasing_vendor_po"
    assert purchasing.schema_migration_risk == "HIGH"
    assert purchasing.production_risk == "PROHIBITED_UNTIL_SEPARATE_AUTHORIZATION"


def test_invalid_collision_active_ownership_and_provenance_fail_closed() -> None:
    collision = raw_bank()
    milestone(collision, "BANK.PUR.001")["collision_domain"] = "invalid/domain"
    with pytest.raises(MilestoneBankIngestionError, match="schema or readiness"):
        ingest_milestone_bank(resign(collision))

    ownership = raw_bank()
    active = milestone(ownership, "BANK.FIELD.001")
    active["owner_decision_required"] = False
    with pytest.raises(MilestoneBankIngestionError, match="active ownership"):
        ingest_milestone_bank(resign(ownership))

    provenance = raw_bank()
    milestone(provenance, "BANK.PUR.001")["repository_evidence"] = ["unknown"]
    with pytest.raises(MilestoneBankIngestionError, match="artifact provenance"):
        ingest_milestone_bank(resign(provenance))


def test_ingestion_has_no_scheduler_execution_or_file_side_effect() -> None:
    manifest_before = MANIFEST_PATH.read_bytes()
    manifest_digest = hashlib.sha256(manifest_before).hexdigest()
    bank_resource = files("app.engineering_control.scheduler").joinpath(
        "milestone-bank.v2.json"
    )
    assert bank_resource.name == "milestone-bank.v2.json"
    assert load_milestone_bank_projection().ready_milestone_ids
    assert MANIFEST_PATH.read_bytes() == manifest_before
    assert hashlib.sha256(MANIFEST_PATH.read_bytes()).hexdigest() == manifest_digest

    source = (
        REPOSITORY / "backend/app/engineering_control/scheduler/bank.py"
    ).read_text(encoding="utf-8")
    forbidden_runtime_symbols = {
        "EngineeringControlService",
        "SchedulerReconciliationService",
        "EngineeringCommand",
        "EngineeringWorkerCapacity",
        "create_async_engine",
        "AsyncSession",
    }
    assert not any(symbol in source for symbol in forbidden_runtime_symbols)


def test_test_mutations_do_not_change_packaged_bank() -> None:
    before = BANK_PATH.read_bytes()
    mutable = copy.deepcopy(raw_bank())
    mutable["purpose"] = "local mutation"
    assert BANK_PATH.read_bytes() == before
