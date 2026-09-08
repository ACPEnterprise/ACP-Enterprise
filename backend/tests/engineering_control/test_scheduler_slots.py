from app.engineering_control.scheduler.runner import HeadlessRunner
from app.engineering_control.scheduler.slots import (
    SLOTS_BY_WORKER,
    first_free_slot,
    physical_worker_for_capacity,
    validate_slot,
)


def test_nine_slots_are_real_worker_children_with_three_each() -> None:
    assert set(SLOTS_BY_WORKER) == {"OM1", "OM2", "LAP"}
    assert sum(len(slots) for slots in SLOTS_BY_WORKER.values()) == 9
    assert all(len(set(slots)) == 3 for slots in SLOTS_BY_WORKER.values())
    assert len({slot for slots in SLOTS_BY_WORKER.values() for slot in slots}) == 9
    assert physical_worker_for_capacity("ECO") == "OM1"
    assert physical_worker_for_capacity("MIG") == "OM2"


def test_slot_allocation_never_oversubscribes_physical_worker() -> None:
    occupied: set[str] = set()
    allocated = []
    for _ in range(4):
        slot = first_free_slot("ECO", occupied)
        allocated.append(slot)
        if slot is not None:
            occupied.add(slot)
    assert allocated == ["OM1-1", "OM1-2", "OM1-3", None]


def test_slot_is_reusable_after_terminal_completion() -> None:
    occupied = {"LAP-1", "LAP-2", "LAP-3"}
    occupied.remove("LAP-2")
    assert first_free_slot("LAP", occupied) == "LAP-2"


def test_slot_validation_prevents_cross_worker_claim() -> None:
    try:
        validate_slot("OM2-1", "OM1")
    except ValueError as error:
        assert "does not belong" in str(error)
    else:
        raise AssertionError("cross-worker slot claim was accepted")


def test_command_state_parser_preserves_independent_slot_occupancy() -> None:
    queue = "ACP.72H.2026-09-03"
    states, slots = HeadlessRunner._states_and_slots(
        queue,
        [
            (f"{queue}:ONE:OM1-1:{'a' * 40}", "running"),
            (f"{queue}:TWO:OM1-2:{'a' * 40}", "queued"),
        ],
    )
    assert states == {"ONE": "running", "TWO": "queued"}
    assert slots == {"ONE": "OM1-1", "TWO": "OM1-2"}
