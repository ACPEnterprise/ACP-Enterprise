import json
from pathlib import Path

import pytest
from development_factory.coordination import (
    CoordinationError,
    dependency_layers,
    eligible_after_activation,
    load_queue,
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


@pytest.mark.parametrize("dependency", ["MISSING", "OM1-TWO"])
def test_unknown_or_cyclic_dependencies_fail_closed(dependency: str) -> None:
    payload = json.loads(json.dumps(queue_payload()))
    payload["assignments"][0]["depends_on"] = [dependency]
    with pytest.raises(CoordinationError):
        validate_queue(payload)
