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
    assert milestones["BANK.PLAT.002"].current_state == "COMPLETE"
    assert milestones["BANK.PLAT.002"].canonical_milestone_id == "BANK.PLAT.002"
    assert milestones["BANK.PLAT.002"].completion_commit_sha == (
        "b88a48d37da0343e49ad916bd0901beb85303c35"
    )
    assert milestones["BANK.PLAT.003"].current_state == "COMPLETE"
    assert milestones["BANK.PLAT.003"].canonical_milestone_id == "BANK.PLAT.003"
    assert milestones["BANK.PLAT.003"].completion_commit_sha == (
        "e7002e9c15745e8236cca7af8265a432243e4b74"
    )
    assert milestones["BANK.PLAT.004"].current_state == "COMPLETE"
    assert milestones["BANK.PLAT.004"].canonical_milestone_id == "BANK.PLAT.004"
    assert milestones["BANK.PLAT.004"].completion_commit_sha == (
        "6f051c8b549298790f51795b42c1644c0f4f131f"
    )
    assert milestones["BANK.PUR.002"].current_state == "COMPLETE"
    assert milestones["BANK.PUR.002"].canonical_milestone_id == "PUR.2"
    assert milestones["BANK.PUR.002"].completion_commit_sha == (
        "04d74278b914b73ca96838128980218fced32546"
    )
    assert milestones["BANK.PUR.003"].current_state == "EXECUTABLE"
    assert milestones["BANK.PLAT.005"].current_state == "EXECUTABLE"
    assert "BANK.PUR.001" not in projection.executable_milestone_ids
    assert "BANK.PLAT.001" not in projection.executable_milestone_ids
    assert "BANK.PUR.002" not in projection.executable_milestone_ids
    assert "BANK.PUR.003" in projection.executable_milestone_ids
    assert "BANK.PLAT.002" not in projection.executable_milestone_ids
    assert "BANK.PLAT.003" not in projection.executable_milestone_ids
    assert "BANK.PLAT.004" not in projection.executable_milestone_ids
    assert "BANK.PLAT.005" in projection.executable_milestone_ids
    assert "BANK.BEA.001" in projection.executable_milestone_ids

    accounting = milestones["BANK.ACC.001"]
    assert accounting.current_state == "COMPLETE"
    assert accounting.canonical_milestone_id == "ACC.IC.1"
    assert accounting.completion_commit_sha == (
        "65377ad5cba31c0945324965f81dd60e7102174c"
    )
    posting_acceptance = milestones["BANK.ACC.002"]
    assert posting_acceptance.current_state == "BLOCKED_FINANCE_DECISION"
    assert posting_acceptance.blocked_reasons == ("finance_decision_required",)


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


def test_platform_002_acceptance_changes_only_itself_and_direct_successor() -> None:
    bank = load_milestone_bank()
    current = _by_id(load_current_readiness_projection())
    raw = _authority_raw()
    raw["completion_evidence"] = [
        item
        for item in raw["completion_evidence"]  # type: ignore[union-attr]
        if item["bank_milestone_id"]
        not in {"BANK.PLAT.002", "BANK.PLAT.003", "BANK.PLAT.004"}
    ]
    prior = _by_id(
        evaluate_readiness(bank, ingest_authority_snapshot(_resign(raw), bank))
    )

    changed = {
        milestone_id
        for milestone_id in current
        if current[milestone_id].current_state != prior[milestone_id].current_state
    }

    assert changed == {
        "BANK.PLAT.002",
        "BANK.PLAT.003",
        "BANK.PLAT.004",
        "BANK.PLAT.005",
    }


def test_platform_003_acceptance_changes_only_itself_and_direct_successor() -> None:
    bank = load_milestone_bank()
    current = _by_id(load_current_readiness_projection())
    raw = _authority_raw()
    evidence = raw["completion_evidence"]
    assert isinstance(evidence, list)
    plat_003 = next(
        item for item in evidence if item["bank_milestone_id"] == "BANK.PLAT.003"
    )
    assert (
        "3892678346c7054803e7f16362d1d7663218f3ff30a3fe6d6860555e4042caef"
        in plat_003["evidence_reference"]
    )
    raw["completion_evidence"] = [
        item
        for item in evidence
        if item["bank_milestone_id"] not in {"BANK.PLAT.003", "BANK.PLAT.004"}
    ]
    prior = _by_id(
        evaluate_readiness(bank, ingest_authority_snapshot(_resign(raw), bank))
    )

    changed = {
        milestone_id
        for milestone_id in current
        if current[milestone_id].current_state != prior[milestone_id].current_state
    }

    assert changed == {"BANK.PLAT.003", "BANK.PLAT.004", "BANK.PLAT.005"}


def test_platform_004_acceptance_changes_only_itself_and_direct_successor() -> None:
    bank = load_milestone_bank()
    current = _by_id(load_current_readiness_projection())
    raw = _authority_raw()
    evidence = raw["completion_evidence"]
    assert isinstance(evidence, list)
    plat_004 = next(
        item for item in evidence if item["bank_milestone_id"] == "BANK.PLAT.004"
    )
    assert plat_004["authoritative_commit_sha"] == (
        "6f051c8b549298790f51795b42c1644c0f4f131f"
    )
    assert (
        "49e35f171ac657be66727fa24f5311806fb27203dff8e4709181f62e12b85b43"
        in plat_004["evidence_reference"]
    )
    raw["completion_evidence"] = [
        item for item in evidence if item["bank_milestone_id"] != "BANK.PLAT.004"
    ]
    prior = _by_id(
        evaluate_readiness(bank, ingest_authority_snapshot(_resign(raw), bank))
    )

    changed = {
        milestone_id
        for milestone_id in current
        if current[milestone_id].current_state != prior[milestone_id].current_state
    }

    assert changed == {"BANK.PLAT.004", "BANK.PLAT.005"}


def test_pur_002_acceptance_changes_only_itself_and_direct_successor() -> None:
    bank = load_milestone_bank()
    current = _by_id(load_current_readiness_projection())
    raw = _authority_raw()
    raw["completion_evidence"] = [
        item
        for item in raw["completion_evidence"]  # type: ignore[union-attr]
        if item["bank_milestone_id"] != "BANK.PUR.002"
    ]
    prior = _by_id(
        evaluate_readiness(bank, ingest_authority_snapshot(_resign(raw), bank))
    )

    changed = {
        milestone_id
        for milestone_id in current
        if current[milestone_id].current_state != prior[milestone_id].current_state
    }

    assert changed == {"BANK.PUR.002", "BANK.PUR.003"}


@pytest.mark.parametrize(
    ("milestone_id", "expected"),
    [
        ("BANK.CRM.001", "BLOCKED_OWNER_DECISION"),
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
            "bank_milestone_id": "BANK.PUR.003",
            "owner_reference": "authoritative-reservation:example",
            "collision_domain": "purchasing_vendor_po",
        }
    ]
    authority = ingest_authority_snapshot(_resign(raw), bank)
    milestone = _by_id(evaluate_readiness(bank, authority))["BANK.PLAT.001"]
    assert milestone.current_state == "COMPLETE"
    purchasing = _by_id(evaluate_readiness(bank, authority))["BANK.PUR.004"]
    assert purchasing.current_state in {"BLOCKED_DEPENDENCY", "BLOCKED_COLLISION"}


def test_collision_blocks_dependency_ready_candidate() -> None:
    bank = load_milestone_bank()
    raw = _authority_raw()
    raw["completion_evidence"] = [
        item
        for item in raw["completion_evidence"]  # type: ignore[union-attr]
        if item["bank_milestone_id"] not in {"BANK.PLAT.001", "BANK.PLAT.002"}
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
    accounting = next(
        item
        for item in authority.completion_evidence
        if item.bank_milestone_id == "BANK.ACC.001"
    )
    assert accounting.canonical_milestone_id == "ACC.IC.1"
    assert "QBO evidence" in accounting.evidence_reference
    assert "remains non-authoritative" in accounting.evidence_reference
    assert not any(
        item.bank_milestone_id == "BANK.ACC.001"
        for item in authority.identity_reconciliation_required
    )
