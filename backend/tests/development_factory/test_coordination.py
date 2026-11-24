import json
from pathlib import Path

import pytest
from development_factory.coordination import (
    CoordinationError,
    dependency_layers,
    eligible_after_activation,
    load_queue,
    validate_inventory,
    validate_queue,
)


def queue_payload() -> dict[str, object]:
    return {
        "schema_version": "twelfthats.continuous-engineering-queue.v1",
        "status": "PREPARED_PENDING_MACHINE_ACTIVATION",
        "assignments": [
            {
                "id": "LAP-ONE",
                "lane": "LAPTOP_MASTER",
                "priority": "P0",
                "state": "READY_AFTER_INVENTORY",
                "depends_on": [],
                "objective": "A bounded test assignment.",
            },
            {
                "id": "OM1-TWO",
                "lane": "OM1",
                "priority": "P1",
                "state": "BLOCKED_DEPENDENCY",
                "depends_on": ["LAP-ONE"],
                "objective": "A dependent test assignment.",
            },
        ],
    }


def test_loads_repository_queue_and_projects_only_activated_lanes() -> None:
    queue = load_queue(Path(__file__).parents[3])
    assert len(queue.assignments) == 12
    assert eligible_after_activation(queue, ()) == ()


def test_dependency_layers_and_activation_projection() -> None:
    queue = validate_queue(queue_payload())
    assert dependency_layers(queue) == (("LAP-ONE",), ("OM1-TWO",))
    assert eligible_after_activation(queue, ("LAPTOP_MASTER",)) == ("LAP-ONE",)


def test_machine_inventory_requires_secret_free_safety_flags() -> None:
    receipt = {
        "schema": "twelfthats.machine-inventory.v1",
        "role_claimed": "OM1",
        "host": {
            "hostname": "om1",
            "os": "macOS",
            "machine": "arm64",
            "python": "3.12",
        },
        "repository": {
            "root": "/repo",
            "branch": "work/om1",
            "head": "a" * 40,
            "origin": "https://example.invalid/repo.git",
        },
        "safety": {
            "private_keys_read": False,
            "environment_values_dumped": False,
            "git_mutation_performed": False,
            "docker_container_started": False,
        },
    }
    assert validate_inventory(receipt)["role_claimed"] == "OM1"
    receipt["safety"]["private_keys_read"] = True
    with pytest.raises(CoordinationError):
        validate_inventory(receipt)


@pytest.mark.parametrize("dependency", ["MISSING", "OM1-TWO"])
def test_unknown_or_cyclic_dependencies_fail_closed(dependency: str) -> None:
    payload = json.loads(json.dumps(queue_payload()))
    payload["assignments"][0]["depends_on"] = [dependency]
    with pytest.raises(CoordinationError):
        validate_queue(payload)
