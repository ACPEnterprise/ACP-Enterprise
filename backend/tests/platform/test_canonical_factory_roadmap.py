from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ROADMAP = ROOT / "docs" / "factory" / "acp_full_system_roadmap.yaml"
COMMAND = ROOT / "scripts" / "factory-roadmap"


def roadmap() -> dict[str, object]:
    return json.loads(ROADMAP.read_text(encoding="utf-8"))


def test_roadmap_maps_all_original_families_and_assigns_every_item() -> None:
    data = roadmap()
    milestones = data["milestones"]
    assert isinstance(milestones, list)
    assert len(milestones) == 60
    assert sorted(
        item["original_milestone_number"]
        for item in milestones
        if "original_milestone_number" in item
    ) == list(range(1, 37))
    assert {item["owning_factory"] for item in milestones} == {
        "OM1",
        "OM2",
        "LAPTOP",
    }
    assert all(item["preferred_worker_lane"] for item in milestones)


def test_migration_children_have_complete_truth_accounting() -> None:
    data = roadmap()
    children = [
        item for item in data["milestones"] if item["id"].startswith("MIG.COMPLETENESS.")
    ]
    assert len(children) == 9
    required = {
        "ACQUIRED",
        "RECONCILED",
        "NATIVE_BOUND",
        "PENDING_ADMISSION",
        "HELD",
        "AMBIGUOUS",
        "UNEXPLAINED",
        "BETA_OPERABLE",
    }
    assert all(set(item["migration_completeness"]) == required for item in children)
    customer = next(item for item in children if item["id"].endswith("CUSTOMERS"))
    assert customer["migration_completeness"]["NATIVE_BOUND"] == "2069"
    assert customer["migration_completeness"]["PENDING_ADMISSION"] == "2241_ACCEPTED_UNBOUND"
    assert customer["migration_completeness"]["BETA_OPERABLE"] == "FAIL"


def test_controller_validator_and_pull_are_deterministic() -> None:
    validated = subprocess.run(
        [str(COMMAND), "validate"],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )
    assert validated.returncode == 0, validated.stdout + validated.stderr
    assert "60 milestones" in validated.stdout

    first = subprocess.run(
        [str(COMMAND), "next", "--factory", "OM2"],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )
    second = subprocess.run(
        [str(COMMAND), "next", "--factory", "OM2"],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )
    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    selected = json.loads(first.stdout)
    assert selected["id"] == "PRICEBOOK.REALWORLD.COMPLETION"
    assert selected["priority"] == "P0"
    assert selected["lane"] == "OM2-A"


def test_closed_is_not_inferred_from_deployment() -> None:
    data = roadmap()
    by_id = {item["id"]: item for item in data["milestones"]}
    pricebook = by_id["PRICEBOOK.OWNER.OPERABILITY"]
    assert pricebook["beta_deployment_status"] == "DEPLOYED_BETA"
    assert pricebook["owner_acceptance_status"] == "OWNER_ACCEPTANCE_REQUIRED"
    assert pricebook["lifecycle_status"] != "CLOSED"
    assert by_id["BETA.DOMAIN.ACTIVATION"]["lifecycle_status"] == "CLOSED"
