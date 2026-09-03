"""Fail-closed headless factory assignment proposals.

This module deliberately produces proposals only. Durable scheduler activation,
command creation, and worker credential changes remain existing authenticated
control-plane responsibilities.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .readiness import CurrentReadinessProjection

CapacityIdentity = Literal["OM1", "OM2", "MIG", "ECO", "LAP"]
ExecutionState = Literal["queued", "starting", "running", "completed", "failed"]
ProposalKind = Literal["activate", "refill", "reconcile"]


class HeadlessModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ApprovedQueueItem(HeadlessModel):
    milestone_id: str = Field(pattern=r"^BANK\.[A-Z0-9]+\.[0-9]{3}$")
    capacity_identity: CapacityIdentity


class ExecutionObservation(HeadlessModel):
    milestone_id: str = Field(pattern=r"^BANK\.[A-Z0-9]+\.[0-9]{3}$")
    capacity_identity: CapacityIdentity
    state: ExecutionState
    heartbeat_at: datetime | None = None

    @model_validator(mode="after")
    def require_heartbeat_for_active_execution(self) -> ExecutionObservation:
        if self.state in {"starting", "running"} and self.heartbeat_at is None:
            raise ValueError("active execution requires heartbeat evidence")
        return self


class HeadlessProposal(HeadlessModel):
    kind: ProposalKind
    milestone_id: str
    capacity_identity: CapacityIdentity
    reason: str


class HeadlessPlan(HeadlessModel):
    authority_fingerprint: str
    proposals: tuple[HeadlessProposal, ...]
    blocked: tuple[str, ...]


def propose_headless_capacity(
    readiness: CurrentReadinessProjection,
    approved_queue: Sequence[ApprovedQueueItem],
    executions: Sequence[ExecutionObservation],
    successors: Mapping[str, Sequence[str]],
    *,
    now: datetime,
    stale_after_seconds: int = 300,
) -> HeadlessPlan:
    """Propose bounded assignments without mutating scheduler or worker state."""

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if stale_after_seconds <= 0:
        raise ValueError("stale threshold must be positive")
    by_id = {item.milestone_id: item for item in readiness.milestones}
    approved_ids = [item.milestone_id for item in approved_queue]
    if len(approved_ids) != len(set(approved_ids)):
        raise ValueError("approved queue contains duplicate milestone identity")
    unknown = set(approved_ids) - set(by_id)
    if unknown:
        raise ValueError(f"approved queue references unknown milestones: {sorted(unknown)}")
    execution_ids = [item.milestone_id for item in executions]
    if len(execution_ids) != len(set(execution_ids)):
        raise ValueError("execution evidence is ambiguous")

    proposals: list[HeadlessProposal] = []
    blocked: list[str] = []
    occupied: set[CapacityIdentity] = set()
    completed: list[ExecutionObservation] = []
    checked = now.astimezone(timezone.utc)
    for execution in executions:
        if execution.state == "completed":
            completed.append(execution)
            continue
        if execution.state in {"queued", "starting", "running"}:
            occupied.add(execution.capacity_identity)
        if execution.state in {"starting", "running"}:
            assert execution.heartbeat_at is not None
            heartbeat = execution.heartbeat_at
            if heartbeat.tzinfo is None or heartbeat.utcoffset() is None:
                raise ValueError("execution heartbeat must be timezone-aware")
            age = (checked - heartbeat.astimezone(timezone.utc)).total_seconds()
            if age > stale_after_seconds:
                proposals.append(
                    HeadlessProposal(
                        kind="reconcile",
                        milestone_id=execution.milestone_id,
                        capacity_identity=execution.capacity_identity,
                        reason="stale heartbeat requires reconciliation; automatic retry is prohibited",
                    )
                )

    queue_by_id = {item.milestone_id: item for item in approved_queue}
    refill_ids = {
        successor_id
        for execution in completed
        for successor_id in successors.get(execution.milestone_id, ())
        if successor_id in queue_by_id
    }

    def offer(item: ApprovedQueueItem, kind: Literal["activate", "refill"]) -> None:
        current = by_id[item.milestone_id]
        if current.current_state != "EXECUTABLE":
            blocked.append(f"{item.milestone_id}:{current.current_state}")
            return
        if item.capacity_identity in occupied:
            blocked.append(f"{item.milestone_id}:capacity_occupied:{item.capacity_identity}")
            return
        proposals.append(
            HeadlessProposal(
                kind=kind,
                milestone_id=item.milestone_id,
                capacity_identity=item.capacity_identity,
                reason="explicit owner-approved executable queue item",
            )
        )
        occupied.add(item.capacity_identity)

    active_ids = set(execution_ids)
    for execution in completed:
        for successor_id in successors.get(execution.milestone_id, ()):
            successor = queue_by_id.get(successor_id)
            if successor is not None and successor_id not in active_ids:
                offer(successor, "refill")
                break

    for item in approved_queue:
        if item.milestone_id not in active_ids and item.milestone_id not in refill_ids:
            offer(item, "activate")

    return HeadlessPlan(
        authority_fingerprint=readiness.fingerprint,
        proposals=tuple(proposals),
        blocked=tuple(sorted(set(blocked))),
    )


__all__ = [
    "ApprovedQueueItem",
    "ExecutionObservation",
    "HeadlessPlan",
    "HeadlessProposal",
    "propose_headless_capacity",
]
