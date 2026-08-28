import hashlib
import json
from collections import Counter
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[3]
BANK_PATH = (
    REPOSITORY
    / "backend/app/engineering_control/scheduler/milestone-bank.v2.json"
)
SCHEMA_PATH = REPOSITORY / "docs/project/schemas/milestone-bank-v2.schema.json"
STARTING_SHA = "1f012258cba67300c3481953aa18a62e12e5b634"


def load_bank() -> dict[str, object]:
    return json.loads(BANK_PATH.read_text(encoding="utf-8"))


def test_bank_is_planning_only_counted_and_fingerprinted() -> None:
    bank = load_bank()
    fingerprint = bank.pop("fingerprint")
    canonical = json.dumps(bank, sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(canonical.encode()).hexdigest() == fingerprint
    assert bank["bank_id"] == "BANK.2"
    assert bank["authoritative_start_sha"] == STARTING_SHA
    assert bank["activation_semantics"] == "NONE_PLANNING_ONLY"
    assert 200 <= len(bank["milestones"]) <= 300  # type: ignore[arg-type]
    assert SCHEMA_PATH.is_file()


def test_bank_ids_dependencies_and_successors_form_a_dag() -> None:
    milestones = load_bank()["milestones"]
    assert isinstance(milestones, list)
    by_id = {item["milestone_id"]: item for item in milestones}
    assert len(by_id) == len(milestones) == 250
    assert len({item["name"].casefold() for item in milestones}) == 250
    for milestone_id, item in by_id.items():
        assert set(item["dependencies"]) <= set(by_id)
        assert set(item["successor_ids"]) <= set(by_id)
        for predecessor in item["dependencies"]:
            assert milestone_id in by_id[predecessor]["successor_ids"]
        for successor in item["successor_ids"]:
            assert milestone_id in by_id[successor]["dependencies"]

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(milestone_id: str) -> None:
        assert milestone_id not in visiting, f"cycle at {milestone_id}"
        if milestone_id in visited:
            return
        visiting.add(milestone_id)
        for predecessor in by_id[milestone_id]["dependencies"]:
            visit(predecessor)
        visiting.remove(milestone_id)
        visited.add(milestone_id)

    for milestone_id in by_id:
        visit(milestone_id)
    assert visited == set(by_id)


def test_readiness_is_fail_closed_and_current_ownership_is_not_ready() -> None:
    milestones = load_bank()["milestones"]
    assert isinstance(milestones, list)
    states = Counter(item["readiness_state"] for item in milestones)
    assert states == {
        "BLOCKED_DEPENDENCY": 231,
        "BLOCKED_OWNER_DECISION": 14,
        "BLOCKED_FINANCE_DECISION": 2,
        "BLOCKED_EXTERNAL": 1,
        "READY": 2,
    }
    ready = {item["milestone_id"] for item in milestones if item["readiness_state"] == "READY"}
    assert ready == {"BANK.PUR.001", "BANK.BEA.001"}
    for item in milestones:
        if item["readiness_state"] == "READY":
            assert item["dependencies"] == []
            assert item["ownership_state"] == "UNOWNED"
            assert not item["owner_decision_required"]
            assert not item["finance_decision_required"]
            assert item["external_gate"] == "none"
        if item["ownership_state"] == "ACTIVE_OWNED":
            assert item["readiness_state"] != "READY"


def test_records_contain_execution_and_acceptance_boundaries() -> None:
    milestones = load_bank()["milestones"]
    assert isinstance(milestones, list)
    required = {
        "milestone_id",
        "name",
        "domain",
        "objective",
        "priority",
        "dependencies",
        "dependency_type",
        "readiness_conditions",
        "implementation_boundary",
        "excluded_scope",
        "likely_repository_areas",
        "collision_domain",
        "owner_decision_required",
        "finance_decision_required",
        "external_gate",
        "schema_migration_risk",
        "production_risk",
        "validation_contract",
        "completion_evidence",
        "successor_ids",
    }
    for item in milestones:
        assert required <= set(item)
        assert item["production_risk"] == "PROHIBITED_UNTIL_SEPARATE_AUTHORIZATION"
        assert item["validation_contract"]
        assert item["completion_evidence"]
