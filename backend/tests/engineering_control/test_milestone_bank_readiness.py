from __future__ import annotations

import copy
import json
from importlib.resources import files

import pytest

from app.engineering_control.scheduler.bank import load_milestone_bank
from app.engineering_control.scheduler.readiness import (
    ReadinessEvaluationError,
    authority_fingerprint,
    evaluate_readiness,
    ingest_authority_snapshot,
    load_authority_snapshot,
    load_current_readiness_projection,
)


def _authority_raw() -> dict[str, object]:
    path = files("app.engineering_control.scheduler").joinpath(
        "milestone-authority.v1.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def _resign(raw: dict[str, object]) -> dict[str, object]:
    raw = copy.deepcopy(raw)
    raw.pop("fingerprint", None)
    return {**raw, "fingerprint": authority_fingerprint(raw)}


def _by_id(projection: object) -> dict[str, object]:
    return {item.milestone_id: item for item in projection.milestones}  # type: ignore[attr-defined]


def _bank_with_unowned(milestone_id: str):
    bank = load_milestone_bank()
    records = tuple(
        item.model_copy(update={"ownership_state": "UNOWNED"})
        if item.milestone_id == milestone_id
        else item
        for item in bank.milestones
    )
    return bank.model_copy(update={"milestones": records})


def test_current_projection_reconciles_completion_and_releases_successor() -> None:
    projection = load_current_readiness_projection()
    milestones = _by_id(projection)

    assert milestones["BANK.PUR.001"].current_state == "COMPLETE"
    assert milestones["BANK.PUR.001"].planning_state == "PLANNED_READY"
    assert milestones["BANK.PUR.001"].canonical_milestone_id == "PUR.1"
    assert milestones["BANK.PUR.001"].completion_commit_sha == (
        "88285c7c0879d8df7b42659a9d25c64e5b58a27b"
    )
    assert milestones["BANK.PLAT.001"].current_state == "COMPLETE"
    assert milestones["BANK.PLAT.001"].canonical_milestone_id == "BANK.PLAT.001"
    assert milestones["BANK.PLAT.001"].completion_commit_sha == (
        "0f6559ecddb7ca3854c79ea7b5cb31432318976a"
    )
    assert milestones["BANK.PUR.002"].current_state == "EXECUTABLE"
    assert milestones["BANK.PLAT.002"].current_state == "EXECUTABLE"
    assert "BANK.PUR.001" not in projection.executable_milestone_ids
    assert "BANK.PLAT.001" not in projection.executable_milestone_ids
    assert "BANK.PUR.002" in projection.executable_milestone_ids
    assert "BANK.PLAT.002" in projection.executable_milestone_ids
    assert "BANK.BEA.001" in projection.executable_milestone_ids


def test_unresolved_predecessor_blocks_successor() -> None:
    bank = load_milestone_bank()
    raw = _authority_raw()
    raw["completion_evidence"] = [
        item
        for item in raw["completion_evidence"]  # type: ignore[union-attr]
        if item["bank_milestone_id"] not in {"BANK.PUR.001", "BANK.PLAT.001"}
    ]
    authority = ingest_authority_snapshot(_resign(raw), bank)

    milestone = _by_id(evaluate_readiness(bank, authority))["BANK.PLAT.001"]
    assert milestone.current_state == "BLOCKED_DEPENDENCY"
    assert milestone.blocked_reasons == ("dependency_not_complete:BANK.PUR.001",)


@pytest.mark.parametrize(
    ("milestone_id", "expected"),
    [
        ("BANK.CRM.001", "BLOCKED_OWNER_DECISION"),
        ("BANK.ACC.001", "BLOCKED_FINANCE_DECISION"),
        ("BANK.MIG.001", "BLOCKED_EXTERNAL"),
    ],
)
def test_unresolved_gates_block(milestone_id: str, expected: str) -> None:
    bank = _bank_with_unowned(milestone_id)
    raw = _authority_raw()
    raw["identity_reconciliation_required"] = [
        item
        for item in raw["identity_reconciliation_required"]  # type: ignore[union-attr]
        if item["bank_milestone_id"] != milestone_id
    ]
    authority = ingest_authority_snapshot(_resign(raw), bank)
    milestone = _by_id(evaluate_readiness(bank, authority))[milestone_id]
    assert milestone.current_state == expected


def test_active_ownership_blocks_duplicate_selection() -> None:
    projection = load_current_readiness_projection()
    milestone = _by_id(projection)["BANK.CRM.001"]
    assert milestone.current_state == "ACTIVE_OWNED"
    assert milestone.milestone_id not in projection.executable_milestone_ids


def test_packaged_ambiguous_historical_identities_fail_closed_per_record() -> None:
    projection = load_current_readiness_projection()
    assert projection.ambiguous_identity_mappings == (
        "BANK.ACC.001",
        "BANK.ECO.001",
        "BANK.MIG.001",
    )
    assert all(
        _by_id(projection)[milestone_id].current_state == "INVALID_AUTHORITY"
        for milestone_id in projection.ambiguous_identity_mappings
    )


def test_active_collision_domain_blocks_other_work() -> None:
    bank = load_milestone_bank()
    raw = _authority_raw()
    raw["active_ownership"] = [
        {
            "bank_milestone_id": "BANK.PUR.002",
            "owner_reference": "authoritative-reservation:example",
            "collision_domain": "purchasing_vendor_po",
        }
    ]
    authority = ingest_authority_snapshot(_resign(raw), bank)
    milestone = _by_id(evaluate_readiness(bank, authority))["BANK.PLAT.001"]
    assert milestone.current_state == "COMPLETE"
    purchasing = _by_id(evaluate_readiness(bank, authority))["BANK.PUR.003"]
    assert purchasing.current_state in {"BLOCKED_DEPENDENCY", "BLOCKED_COLLISION"}


def test_collision_blocks_dependency_ready_candidate() -> None:
    bank = load_milestone_bank()
    raw = _authority_raw()
    raw["completion_evidence"] = [
        item
        for item in raw["completion_evidence"]  # type: ignore[union-attr]
        if item["bank_milestone_id"] != "BANK.PLAT.001"
    ]
    raw["active_ownership"] = [
        {
            "bank_milestone_id": "BANK.PLAT.002",
            "owner_reference": "authoritative-reservation:platform",
            "collision_domain": "platform_shared",
        }
    ]
    authority = ingest_authority_snapshot(_resign(raw), bank)
    milestone = _by_id(evaluate_readiness(bank, authority))["BANK.PLAT.001"]
    assert milestone.current_state == "BLOCKED_COLLISION"


def test_ambiguous_identity_mapping_fails_closed() -> None:
    bank = load_milestone_bank()
    raw = _authority_raw()
    raw["completion_evidence"].append(  # type: ignore[union-attr]
        {
            "bank_milestone_id": "BANK.PUR.001",
            "canonical_milestone_id": "PUR.HISTORICAL",
            "evidence_kind": "AUTHORITATIVE_INTEGRATION_ACCEPTANCE",
            "authoritative_commit_sha": "88285c7c0879d8df7b42659a9d25c64e5b58a27b",
            "evidence_reference": "contradictory historical identity mapping",
        }
    )
    with pytest.raises(ReadinessEvaluationError, match="ambiguous"):
        ingest_authority_snapshot(_resign(raw), bank)


def test_contradictory_completion_and_ownership_fails_closed() -> None:
    bank = load_milestone_bank()
    raw = _authority_raw()
    raw["active_ownership"] = [
        {
            "bank_milestone_id": "BANK.PUR.001",
            "owner_reference": "conflicting-reservation",
            "collision_domain": "purchasing_vendor_po",
        }
    ]
    with pytest.raises(ReadinessEvaluationError, match="cannot be active"):
        ingest_authority_snapshot(_resign(raw), bank)


def test_projection_is_deterministic_and_has_no_side_effects() -> None:
    before_bank = (
        files("app.engineering_control.scheduler")
        .joinpath("milestone-bank.v2.json")
        .read_bytes()
    )
    before_manifest = (
        files("app.engineering_control.scheduler")
        .joinpath("scheduler-manifest.v1.json")
        .read_bytes()
    )

    first = load_current_readiness_projection()
    second = load_current_readiness_projection()

    assert first == second
    assert first.fingerprint == second.fingerprint
    assert len(first.milestones) == 250
    assert (
        before_bank
        == files("app.engineering_control.scheduler")
        .joinpath("milestone-bank.v2.json")
        .read_bytes()
    )
    assert (
        before_manifest
        == files("app.engineering_control.scheduler")
        .joinpath("scheduler-manifest.v1.json")
        .read_bytes()
    )


def test_authority_fingerprint_mismatch_fails_closed() -> None:
    bank = load_milestone_bank()
    raw = _authority_raw()
    raw["authoritative_repository_sha"] = "0" * 40
    with pytest.raises(ReadinessEvaluationError, match="fingerprint"):
        ingest_authority_snapshot(raw, bank)


def test_packaged_authority_is_valid() -> None:
    bank = load_milestone_bank()
    authority = load_authority_snapshot(bank)
    assert authority.bank_fingerprint == bank.fingerprint
