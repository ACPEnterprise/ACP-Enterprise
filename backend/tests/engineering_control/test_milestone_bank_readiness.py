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
    assert milestones["BANK.PLAT.005"].current_state == "COMPLETE"
    assert milestones["BANK.PLAT.005"].canonical_milestone_id == "BANK.PLAT.005"
    assert milestones["BANK.PLAT.005"].completion_commit_sha == (
        "e874fc2aa1c2060fea7706ab7521e779997c2948"
    )
    assert milestones["BANK.PLAT.006"].current_state == "COMPLETE"
    assert milestones["BANK.PLAT.006"].canonical_milestone_id == "BANK.PLAT.006"
    assert milestones["BANK.PLAT.006"].completion_commit_sha == (
        "e37a1ffca0e61f80ca5f7c87e81784276e88b614"
    )
    assert milestones["BANK.PLAT.007"].current_state == "COMPLETE"
    assert milestones["BANK.PLAT.007"].canonical_milestone_id == "BANK.PLAT.007"
    assert milestones["BANK.PLAT.007"].completion_commit_sha == (
        "6b5e8c16121a80852f79a9474e7dabd395d6dba7"
    )
    assert milestones["BANK.PLAT.008"].current_state == "EXECUTABLE"
    assert milestones["BANK.PUR.002"].current_state == "COMPLETE"
    assert milestones["BANK.PUR.002"].canonical_milestone_id == "PUR.2"
    assert milestones["BANK.PUR.002"].completion_commit_sha == (
        "04d74278b914b73ca96838128980218fced32546"
    )
    assert milestones["BANK.PUR.003"].current_state == "COMPLETE"
    assert milestones["BANK.PUR.003"].canonical_milestone_id == "BANK.PUR.003"
    assert milestones["BANK.PUR.003"].completion_commit_sha == (
        "624c69152e54364acb4d157143870d8024c698da"
    )
    assert milestones["BANK.PUR.004"].current_state == "COMPLETE"
    assert milestones["BANK.PUR.004"].canonical_milestone_id == "BANK.PUR.004"
    assert milestones["BANK.PUR.004"].completion_commit_sha == (
        "a95cf5ea85c3c0e26f87babf76d00a4e90a0ffd5"
    )
    assert milestones["BANK.PUR.005"].current_state == "COMPLETE"
    assert milestones["BANK.PUR.005"].canonical_milestone_id == "BANK.PUR.005"
    assert milestones["BANK.PUR.005"].completion_commit_sha == (
        "76f58871db4961e944907ddaa09eda53a1cc5056"
    )
    assert milestones["BANK.PUR.006"].current_state == "COMPLETE"
    assert milestones["BANK.PUR.006"].canonical_milestone_id == "BANK.PUR.006"
    assert milestones["BANK.PUR.006"].completion_commit_sha == (
        "3b6349400bfa675e85a8bb71785507144284ed4f"
    )
    assert milestones["BANK.PUR.007"].current_state == "COMPLETE"
    assert milestones["BANK.PUR.007"].canonical_milestone_id == "BANK.PUR.007"
    assert milestones["BANK.PUR.007"].completion_commit_sha == (
        "8f9eab8355087756648fe12c9d42294b5ee3d2c3"
    )
    assert milestones["BANK.PUR.008"].current_state == "COMPLETE"
    assert milestones["BANK.PUR.008"].canonical_milestone_id == "BANK.PUR.008"
    assert milestones["BANK.PUR.008"].completion_commit_sha == (
        "a6af6ed6a9fbee0f12c13e3489012787275bd09d"
    )
    assert milestones["BANK.PUR.009"].current_state == "EXECUTABLE"
    assert "BANK.PUR.001" not in projection.executable_milestone_ids
    assert "BANK.PLAT.001" not in projection.executable_milestone_ids
    assert "BANK.PUR.002" not in projection.executable_milestone_ids
    assert "BANK.PUR.003" not in projection.executable_milestone_ids
    assert "BANK.PUR.004" not in projection.executable_milestone_ids
    assert "BANK.PUR.005" not in projection.executable_milestone_ids
    assert "BANK.PUR.006" not in projection.executable_milestone_ids
    assert "BANK.PUR.007" not in projection.executable_milestone_ids
    assert "BANK.PUR.008" not in projection.executable_milestone_ids
    assert "BANK.PUR.009" in projection.executable_milestone_ids
    assert "BANK.PLAT.002" not in projection.executable_milestone_ids
    assert "BANK.PLAT.003" not in projection.executable_milestone_ids
    assert "BANK.PLAT.004" not in projection.executable_milestone_ids
    assert "BANK.PLAT.005" not in projection.executable_milestone_ids
    assert "BANK.PLAT.006" not in projection.executable_milestone_ids
    assert "BANK.PLAT.007" not in projection.executable_milestone_ids
    assert "BANK.PLAT.008" in projection.executable_milestone_ids
    assert milestones["BANK.BEA.001"].current_state == "COMPLETE"
    assert milestones["BANK.BEA.001"].canonical_milestone_id == "BANK.BEA.001"
    assert milestones["BANK.BEA.001"].completion_commit_sha == (
        "0f6559ecddb7ca3854c79ea7b5cb31432318976a"
    )
    assert milestones["BANK.BEA.002"].current_state == "COMPLETE"
    assert milestones["BANK.BEA.002"].completion_commit_sha == (
        "e82e19bdc012d60f663fed012bc5797175abde98"
    )
    assert milestones["BANK.BEA.003"].current_state == "COMPLETE"
    assert milestones["BANK.BEA.003"].completion_commit_sha == (
        "cce44ec4227418b7543d05b977b81c9656e21f25"
    )
    assert milestones["BANK.BEA.004"].current_state == "COMPLETE"
    assert milestones["BANK.BEA.004"].completion_commit_sha == (
        "2a6a83c9a6a7e20ab9ce5af7964ed27ae28e27d0"
    )
    assert milestones["BANK.BEA.005"].current_state == "EXECUTABLE"
    assert "BANK.BEA.001" not in projection.executable_milestone_ids
    assert "BANK.BEA.002" not in projection.executable_milestone_ids
    assert "BANK.BEA.003" not in projection.executable_milestone_ids
    assert "BANK.BEA.004" not in projection.executable_milestone_ids
    assert "BANK.BEA.005" in projection.executable_milestone_ids

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


def test_beacon_004_acceptance_releases_only_direct_successor() -> None:
    bank = load_milestone_bank()
    current = _by_id(load_current_readiness_projection())
    raw = _authority_raw()
    evidence = raw["completion_evidence"]
    assert isinstance(evidence, list)
    bea_004 = next(
        item for item in evidence if item["bank_milestone_id"] == "BANK.BEA.004"
    )
    assert bea_004["authoritative_commit_sha"] == (
        "2a6a83c9a6a7e20ab9ce5af7964ed27ae28e27d0"
    )
    assert (
        "ccebae77da16c3f1044a03af88c8a734a6cc7662e95406132a9b405eaaf362b1"
        in bea_004["evidence_reference"]
    )
    raw["completion_evidence"] = [
        item for item in evidence if item["bank_milestone_id"] != "BANK.BEA.004"
    ]
    prior = _by_id(
        evaluate_readiness(bank, ingest_authority_snapshot(_resign(raw), bank))
    )

    changed = {
        milestone_id
        for milestone_id in current
        if current[milestone_id].current_state != prior[milestone_id].current_state
    }
    assert changed == {"BANK.BEA.004", "BANK.BEA.005"}


def test_platform_002_acceptance_changes_only_itself_and_direct_successor() -> None:
    bank = load_milestone_bank()
    current = _by_id(load_current_readiness_projection())
    raw = _authority_raw()
    raw["completion_evidence"] = [
        item
        for item in raw["completion_evidence"]  # type: ignore[union-attr]
        if item["bank_milestone_id"]
        not in {
            "BANK.PLAT.002",
            "BANK.PLAT.003",
            "BANK.PLAT.004",
            "BANK.PLAT.005",
        }
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
        if item["bank_milestone_id"]
        not in {"BANK.PLAT.003", "BANK.PLAT.004", "BANK.PLAT.005"}
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
        "BANK.PLAT.003",
        "BANK.PLAT.004",
        "BANK.PLAT.005",
    }


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
        item
        for item in evidence
        if item["bank_milestone_id"] not in {"BANK.PLAT.004", "BANK.PLAT.005"}
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


def test_platform_005_acceptance_changes_only_itself_and_direct_successor() -> None:
    bank = load_milestone_bank()
    current = _by_id(load_current_readiness_projection())
    raw = _authority_raw()
    evidence = raw["completion_evidence"]
    assert isinstance(evidence, list)
    plat_005 = next(
        item for item in evidence if item["bank_milestone_id"] == "BANK.PLAT.005"
    )
    assert plat_005["authoritative_commit_sha"] == (
        "e874fc2aa1c2060fea7706ab7521e779997c2948"
    )
    assert (
        "no exactly-once transport or global-ordering claim"
        in plat_005["evidence_reference"]
    )
    raw["completion_evidence"] = [
        item for item in evidence if item["bank_milestone_id"] != "BANK.PLAT.005"
    ]
    prior = _by_id(
        evaluate_readiness(bank, ingest_authority_snapshot(_resign(raw), bank))
    )

    changed = {
        milestone_id
        for milestone_id in current
        if current[milestone_id].current_state != prior[milestone_id].current_state
    }

    assert changed == {"BANK.PLAT.005"}


def test_platform_006_acceptance_changes_only_itself_and_direct_successor() -> None:
    bank = load_milestone_bank()
    current = _by_id(load_current_readiness_projection())
    raw = _authority_raw()
    evidence = raw["completion_evidence"]
    assert isinstance(evidence, list)
    plat_006 = next(
        item for item in evidence if item["bank_milestone_id"] == "BANK.PLAT.006"
    )
    assert plat_006["authoritative_commit_sha"] == (
        "e37a1ffca0e61f80ca5f7c87e81784276e88b614"
    )
    assert "corrective migration s0j2f4h6k831" in plat_006["evidence_reference"]
    assert "supersedes premature f77cc2f" in plat_006["evidence_reference"]
    assert "no exactly-once external-delivery claim" in plat_006["evidence_reference"]
    raw["completion_evidence"] = [
        item for item in evidence if item["bank_milestone_id"] != "BANK.PLAT.006"
    ]
    prior = _by_id(
        evaluate_readiness(bank, ingest_authority_snapshot(_resign(raw), bank))
    )

    changed = {
        milestone_id
        for milestone_id in current
        if current[milestone_id].current_state != prior[milestone_id].current_state
    }

    assert changed == {"BANK.PLAT.006"}


def test_platform_007_acceptance_changes_only_itself_and_direct_successor() -> None:
    bank = load_milestone_bank()
    current = _by_id(load_current_readiness_projection())
    raw = _authority_raw()
    evidence = raw["completion_evidence"]
    assert isinstance(evidence, list)
    plat_007 = next(
        item for item in evidence if item["bank_milestone_id"] == "BANK.PLAT.007"
    )
    assert plat_007["authoritative_commit_sha"] == (
        "6b5e8c16121a80852f79a9474e7dabd395d6dba7"
    )
    assert (
        "d480e5aa005637e6ade7c4ef8c9316bde8d52a98e5932b65fc7bcf0dc74d2c02"
        in plat_007["evidence_reference"]
    )
    assert (
        "43f3d0cfaa98462e63d4cbd699671d49cb8c5391b769dbba0c61ef5a3fc507bb"
        in plat_007["evidence_reference"]
    )
    raw["completion_evidence"] = [
        item for item in evidence if item["bank_milestone_id"] != "BANK.PLAT.007"
    ]
    prior = _by_id(
        evaluate_readiness(bank, ingest_authority_snapshot(_resign(raw), bank))
    )

    changed = {
        milestone_id
        for milestone_id in current
        if current[milestone_id].current_state != prior[milestone_id].current_state
    }

    assert changed == {"BANK.PLAT.007", "BANK.PLAT.008"}


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

    # PUR.3 has independently accepted evidence, so removing PUR.2 changes
    # only PUR.2 rather than invalidating completed downstream history.
    assert changed == {"BANK.PUR.002"}


def test_pur_003_acceptance_changes_only_itself_and_direct_successor() -> None:
    bank = load_milestone_bank()
    current = _by_id(load_current_readiness_projection())
    raw = _authority_raw()
    raw["completion_evidence"] = [
        item
        for item in raw["completion_evidence"]  # type: ignore[union-attr]
        if item["bank_milestone_id"] != "BANK.PUR.003"
    ]
    prior = _by_id(
        evaluate_readiness(bank, ingest_authority_snapshot(_resign(raw), bank))
    )

    changed = {
        milestone_id
        for milestone_id in current
        if current[milestone_id].current_state != prior[milestone_id].current_state
    }

    # PUR.4 has independently accepted evidence, so removing PUR.3 changes
    # only PUR.3 rather than invalidating completed downstream history.
    assert changed == {"BANK.PUR.003"}


def test_pur_004_end_to_end_acceptance_changes_only_itself_and_successor() -> None:
    bank = load_milestone_bank()
    current = _by_id(load_current_readiness_projection())
    raw = _authority_raw()
    evidence = raw["completion_evidence"]
    assert isinstance(evidence, list)
    pur_004 = next(
        item for item in evidence if item["bank_milestone_id"] == "BANK.PUR.004"
    )
    assert pur_004["authoritative_commit_sha"] == (
        "a95cf5ea85c3c0e26f87babf76d00a4e90a0ffd5"
    )
    assert "f94a95816904d0f84ba9e35da81cad24bafe9814" in pur_004["evidence_reference"]
    assert "eb8c047eb3cb3d44fc183a9ba7239cd8292d806a" in pur_004["evidence_reference"]
    assert "p7g9c1e3h608" in pur_004["evidence_reference"]
    assert "6ced94045c9f71fca35836aa3f4884b3f97de1bb" in pur_004["evidence_reference"]
    raw["completion_evidence"] = [
        item for item in evidence if item["bank_milestone_id"] != "BANK.PUR.004"
    ]
    prior = _by_id(
        evaluate_readiness(bank, ingest_authority_snapshot(_resign(raw), bank))
    )

    changed = {
        milestone_id
        for milestone_id in current
        if current[milestone_id].current_state != prior[milestone_id].current_state
    }

    # PUR.5 has independently accepted evidence, so removing PUR.4 changes
    # only PUR.4 rather than invalidating completed downstream history.
    assert changed == {"BANK.PUR.004"}


def test_pur_005_acceptance_changes_only_itself_and_direct_successor() -> None:
    bank = load_milestone_bank()
    current = _by_id(load_current_readiness_projection())
    raw = _authority_raw()
    evidence = raw["completion_evidence"]
    assert isinstance(evidence, list)
    pur_005 = next(
        item for item in evidence if item["bank_milestone_id"] == "BANK.PUR.005"
    )
    assert pur_005["authoritative_commit_sha"] == (
        "76f58871db4961e944907ddaa09eda53a1cc5056"
    )
    assert "43e95bc6e394d2deb2e73aaea9155fc4596a035f" in pur_005[
        "evidence_reference"
    ]
    assert "t1k3g5i7l942" in pur_005["evidence_reference"]
    assert (
        "aa04e2b347a70d46a00f13a6b71ac97fcda47bf6878fdc86ed8c5c507f54df0c"
        in pur_005["evidence_reference"]
    )
    raw["completion_evidence"] = [
        item for item in evidence if item["bank_milestone_id"] != "BANK.PUR.005"
    ]
    prior = _by_id(
        evaluate_readiness(bank, ingest_authority_snapshot(_resign(raw), bank))
    )

    changed = {
        milestone_id
        for milestone_id in current
        if current[milestone_id].current_state != prior[milestone_id].current_state
    }

    # PUR.6 has independently accepted evidence, so removing PUR.5 changes
    # only PUR.5 rather than invalidating completed downstream history.
    assert changed == {"BANK.PUR.005"}


def test_pur_006_acceptance_changes_only_itself_and_direct_successor() -> None:
    bank = load_milestone_bank()
    current = _by_id(load_current_readiness_projection())
    raw = _authority_raw()
    evidence = raw["completion_evidence"]
    assert isinstance(evidence, list)
    pur_006 = next(
        item for item in evidence if item["bank_milestone_id"] == "BANK.PUR.006"
    )
    assert pur_006["authoritative_commit_sha"] == (
        "3b6349400bfa675e85a8bb71785507144284ed4f"
    )
    raw["completion_evidence"] = [
        item for item in evidence if item["bank_milestone_id"] != "BANK.PUR.006"
    ]
    prior = _by_id(
        evaluate_readiness(bank, ingest_authority_snapshot(_resign(raw), bank))
    )

    changed = {
        milestone_id
        for milestone_id in current
        if current[milestone_id].current_state != prior[milestone_id].current_state
    }

    # PUR.7 has independently accepted evidence, so removing PUR.6 changes
    # only PUR.6 rather than invalidating completed downstream history.
    assert changed == {"BANK.PUR.006"}


def test_pur_007_acceptance_changes_only_itself_and_direct_successor() -> None:
    bank = load_milestone_bank()
    current = _by_id(load_current_readiness_projection())
    raw = _authority_raw()
    evidence = raw["completion_evidence"]
    assert isinstance(evidence, list)
    pur_007 = next(
        item for item in evidence if item["bank_milestone_id"] == "BANK.PUR.007"
    )
    assert pur_007["authoritative_commit_sha"] == (
        "8f9eab8355087756648fe12c9d42294b5ee3d2c3"
    )
    raw["completion_evidence"] = [
        item for item in evidence if item["bank_milestone_id"] != "BANK.PUR.007"
    ]
    prior = _by_id(
        evaluate_readiness(bank, ingest_authority_snapshot(_resign(raw), bank))
    )

    changed = {
        milestone_id
        for milestone_id in current
        if current[milestone_id].current_state != prior[milestone_id].current_state
    }

    # PUR.8 has independently accepted evidence, so removing PUR.7 changes
    # only PUR.7 rather than invalidating completed downstream history.
    assert changed == {"BANK.PUR.007"}


def test_pur_008_acceptance_changes_only_itself_and_direct_successor() -> None:
    bank = load_milestone_bank()
    current = _by_id(load_current_readiness_projection())
    raw = _authority_raw()
    evidence = raw["completion_evidence"]
    assert isinstance(evidence, list)
    pur_008 = next(
        item for item in evidence if item["bank_milestone_id"] == "BANK.PUR.008"
    )
    assert pur_008["authoritative_commit_sha"] == (
        "a6af6ed6a9fbee0f12c13e3489012787275bd09d"
    )
    assert "6877c9af1896931abd9472815357df4966f6ff52c6120057830c96074cfe4af4" in (
        pur_008["evidence_reference"]
    )
    raw["completion_evidence"] = [
        item for item in evidence if item["bank_milestone_id"] != "BANK.PUR.008"
    ]
    prior = _by_id(
        evaluate_readiness(bank, ingest_authority_snapshot(_resign(raw), bank))
    )

    changed = {
        milestone_id
        for milestone_id in current
        if current[milestone_id].current_state != prior[milestone_id].current_state
    }

    assert changed == {"BANK.PUR.008", "BANK.PUR.009"}


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


def test_historical_bank_ownership_does_not_override_current_authority() -> None:
    projection = load_current_readiness_projection()
    milestone = _by_id(projection)["BANK.CRM.001"]
    assert milestone.current_state == "BLOCKED_OWNER_DECISION"
    assert milestone.milestone_id not in projection.executable_milestone_ids


def test_current_authority_ownership_blocks_duplicate_selection() -> None:
    bank = load_milestone_bank()
    raw = _authority_raw()
    raw["active_ownership"] = [
        {
            "bank_milestone_id": "BANK.CRM.001",
            "owner_reference": "current-authority:customer-experience",
            "collision_domain": "customer_identity_timeline",
        }
    ]
    authority = ingest_authority_snapshot(_resign(raw), bank)
    milestone = _by_id(evaluate_readiness(bank, authority))["BANK.CRM.001"]
    assert milestone.current_state == "ACTIVE_OWNED"
    assert milestone.milestone_id not in evaluate_readiness(
        bank, authority
    ).executable_milestone_ids


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
            "bank_milestone_id": "BANK.PUR.009",
            "owner_reference": "authoritative-reservation:example",
            "collision_domain": "purchasing_vendor_po",
        }
    ]
    authority = ingest_authority_snapshot(_resign(raw), bank)
    milestone = _by_id(evaluate_readiness(bank, authority))["BANK.PLAT.001"]
    assert milestone.current_state == "COMPLETE"
    purchasing = _by_id(evaluate_readiness(bank, authority))["BANK.PUR.009"]
    assert purchasing.current_state == "ACTIVE_OWNED"


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
