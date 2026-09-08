"""Logical execution slots backed by real physical worker capacity."""

from __future__ import annotations

from typing import Final, Literal, cast

PhysicalWorker = Literal["OM1", "OM2", "LAP"]
LogicalSlot = Literal[
    "OM1-1",
    "OM1-2",
    "OM1-3",
    "OM2-1",
    "OM2-2",
    "OM2-3",
    "LAP-1",
    "LAP-2",
    "LAP-3",
]

SLOTS_BY_WORKER: Final[dict[PhysicalWorker, tuple[LogicalSlot, ...]]] = {
    "OM1": ("OM1-1", "OM1-2", "OM1-3"),
    "OM2": ("OM2-1", "OM2-2", "OM2-3"),
    "LAP": ("LAP-1", "LAP-2", "LAP-3"),
}

# MIG and ECO remain planning identities, not fabricated machines.  They execute
# on the physical workers that already own those factory lanes.
WORKER_BY_CAPACITY: Final[dict[str, PhysicalWorker]] = {
    "OM1": "OM1",
    "ECO": "OM1",
    "OM2": "OM2",
    "MIG": "OM2",
    "LAP": "LAP",
}


def physical_worker_for_capacity(capacity_identity: str) -> PhysicalWorker:
    try:
        return WORKER_BY_CAPACITY[capacity_identity]
    except KeyError as error:
        raise ValueError(f"unknown capacity identity: {capacity_identity}") from error


def first_free_slot(capacity_identity: str, occupied: set[str]) -> LogicalSlot | None:
    """Return one deterministic unoccupied slot on the owning physical worker."""

    worker = physical_worker_for_capacity(capacity_identity)
    return next(
        (slot for slot in SLOTS_BY_WORKER[worker] if slot not in occupied), None
    )


def validate_slot(slot: str, capacity_identity: str) -> LogicalSlot:
    worker = physical_worker_for_capacity(capacity_identity)
    if slot not in SLOTS_BY_WORKER[worker]:
        raise ValueError("logical slot does not belong to capacity's physical worker")
    return cast(LogicalSlot, slot)


__all__ = [
    "SLOTS_BY_WORKER",
    "LogicalSlot",
    "PhysicalWorker",
    "first_free_slot",
    "physical_worker_for_capacity",
    "validate_slot",
]
