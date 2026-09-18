from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import fmean
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.factory_control.models import (
    FactoryControlEvent,
    FactoryControlSnapshot,
    FactoryLaneState,
)
from app.platform.factory_control.roadmap import (
    FactoryRoadmap,
    load_roadmap,
    safe_event_details,
)
from app.platform.factory_control.schemas import FactoryEventIn

SOURCE_ROADMAP_PATH = (
    Path(__file__).resolve().parents[4] / "docs/factory/acp_full_system_roadmap.yaml"
)
PACKAGED_ROADMAP_PATH = Path(__file__).with_name("data") / "roadmap.json"
PACKAGED_ROADMAP_DIGEST_PATH = PACKAGED_ROADMAP_PATH.with_suffix(".sha256")
STAGES = ("engineering_complete", "beta_complete", "owner_accepted", "closed")


class FactoryEventConflict(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def percent(numerator: float, denominator: float) -> float:
    return round(100 * numerator / denominator, 2) if denominator else 0.0


def calculate_metrics(
    *,
    roadmap: FactoryRoadmap,
    events: list[FactoryControlEvent],
    lanes: list[FactoryLaneState],
    now: datetime,
) -> dict:
    roadmap_codes = {item.code for item in roadmap.milestones}
    milestone_stages: dict[str, set[str]] = defaultdict(set)
    for milestone in roadmap.milestones:
        if milestone.engineering_status in {
            "ENGINEERING_READY",
            "INTEGRATED",
            "DEPLOYED_BETA",
            "CLOSED",
        }:
            milestone_stages[milestone.code].add("engineering_complete")
        if milestone.beta_deployment_status in {"DEPLOYED_BETA", "CLOSED"}:
            milestone_stages[milestone.code].add("beta_complete")
        if milestone.owner_acceptance_status in {"ACCEPTED", "CLOSED"}:
            milestone_stages[milestone.code].add("owner_accepted")
        if milestone.lifecycle_status == "CLOSED":
            milestone_stages[milestone.code].add("closed")
    defect_state: dict[str, bool] = {}
    gate_state: dict[str, bool] = {}
    handoffs: dict[str, datetime] = {}
    pickup_latencies: list[float] = []
    rework = first_pass = 0
    for event in sorted(events, key=lambda item: (item.occurred_at, str(item.id))):
        if event.milestone_code in roadmap_codes and event.event_type in STAGES:
            milestone_stages[event.milestone_code].add(event.event_type)
        identity = str(event.details.get("defect_id", event.milestone_code or event.id))
        if event.event_type == "defect_opened":
            defect_state[identity] = True
        elif event.event_type == "defect_closed":
            defect_state[identity] = False
        gate_id = str(event.details.get("gate_id", event.milestone_code or event.id))
        if event.event_type == "gate_opened":
            gate_state[gate_id] = True
        elif event.event_type == "gate_closed":
            gate_state[gate_id] = False
        handoff_key = str(
            event.details.get("handoff_id", event.milestone_code or event.id)
        )
        if event.event_type == "handoff":
            handoffs[handoff_key] = event.occurred_at
        elif event.event_type == "pickup" and handoff_key in handoffs:
            pickup_latencies.append(
                max(
                    0.0, (event.occurred_at - handoffs.pop(handoff_key)).total_seconds()
                )
            )
        elif event.event_type == "rework_started":
            rework += 1
        elif event.event_type == "first_pass_complete":
            first_pass += 1
    total = len(roadmap.milestones)
    completed_times = {
        milestone: max(
            event.occurred_at
            for event in events
            if event.event_type == "closed" and event.milestone_code == milestone
        )
        for milestone, stages in milestone_stages.items()
        if "closed" in stages
    }.values()
    rates = {
        days: percent(
            sum(stamp >= now - timedelta(days=days) for stamp in completed_times), total
        )
        for days in (1, 3, 7)
    }
    active = sum(lane.lifecycle_state.upper() == "ACTIVE" for lane in lanes)
    completed = sum("closed" in stages for stages in milestone_stages.values())
    attempts = first_pass + rework
    oldest = min(handoffs.values()) if handoffs else None
    return {
        "engineering_percent": percent(
            sum(
                "engineering_complete" in stages for stages in milestone_stages.values()
            ),
            total,
        ),
        "beta_percent": percent(
            sum("beta_complete" in stages for stages in milestone_stages.values()),
            total,
        ),
        "owner_percent": percent(
            sum("owner_accepted" in stages for stages in milestone_stages.values()),
            total,
        ),
        "closed_percent": percent(completed, total),
        "weighted_delivery_percent": round(
            0.5 * rates[1] + 0.3 * rates[3] + 0.2 * rates[7], 2
        ),
        "delivery_1d_percent": rates[1],
        "delivery_3d_percent": rates[3],
        "delivery_7d_percent": rates[7],
        "open_defects": sum(defect_state.values()),
        "open_gates": sum(gate_state.values()),
        "utilization_percent": percent(active, len(lanes)),
        "pickup_latency_seconds": round(fmean(pickup_latencies), 2)
        if pickup_latencies
        else None,
        "queue_depth": sum(lane.queue_depth for lane in lanes),
        "oldest_handoff_seconds": round((now - oldest).total_seconds(), 2)
        if oldest
        else None,
        "rework_rate_percent": percent(rework, attempts),
        "first_pass_yield_percent": percent(first_pass, attempts),
    }


class FactoryControlService:
    @staticmethod
    async def _lock_identity(
        session: AsyncSession, *, company_id: UUID, namespace: str, key: str
    ) -> None:
        identity = f"factory-control:{namespace}:{company_id}:{key}"
        await session.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(identity, 0)))
        )

    def roadmap(self) -> FactoryRoadmap:
        if SOURCE_ROADMAP_PATH.is_file():
            return load_roadmap(SOURCE_ROADMAP_PATH)
        return load_roadmap(
            PACKAGED_ROADMAP_PATH, digest_path=PACKAGED_ROADMAP_DIGEST_PATH
        )

    async def ingest(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        actor_user_id: UUID,
        data: FactoryEventIn,
    ) -> tuple[FactoryControlEvent, bool]:
        details = safe_event_details(data.details)
        await self._lock_identity(
            session,
            company_id=company_id,
            namespace="event",
            key=data.idempotency_key,
        )
        existing = await session.scalar(
            select(FactoryControlEvent).where(
                FactoryControlEvent.company_id == company_id,
                FactoryControlEvent.idempotency_key == data.idempotency_key,
            )
        )
        if existing is not None:
            if (
                existing.lane_code != data.lane_code
                or existing.milestone_code != data.milestone_code
                or existing.event_type != data.event_type
                or existing.lifecycle_state != data.lifecycle_state
                or existing.occurred_at != data.occurred_at
                or existing.details != details
            ):
                raise FactoryEventConflict(
                    "factory event idempotency key was reused with different facts"
                )
            return existing, True
        lane = await session.scalar(
            select(FactoryLaneState)
            .where(
                FactoryLaneState.company_id == company_id,
                FactoryLaneState.lane_code == data.lane_code,
            )
            .with_for_update()
        )
        event = FactoryControlEvent(
            company_id=company_id,
            lane_code=data.lane_code,
            milestone_code=data.milestone_code,
            event_type=data.event_type,
            lifecycle_state=data.lifecycle_state,
            source="controller",
            idempotency_key=data.idempotency_key,
            details=details,
            actor_user_id=actor_user_id,
            occurred_at=data.occurred_at,
            received_at=utc_now(),
        )
        session.add(event)
        if lane is None:
            lane = FactoryLaneState(
                company_id=company_id,
                lane_code=data.lane_code,
                milestone_code=data.milestone_code,
                lifecycle_state=data.lifecycle_state or "idle",
                queue_depth=data.queue_depth,
                active_since=data.occurred_at
                if data.lifecycle_state == "ACTIVE"
                else None,
                last_handoff_at=data.occurred_at
                if data.event_type == "handoff"
                else None,
                last_event_at=data.occurred_at,
                updated_at=utc_now(),
            )
            session.add(lane)
        elif data.occurred_at >= lane.last_event_at:
            was_active = lane.lifecycle_state.upper() == "ACTIVE"
            lane.milestone_code = data.milestone_code
            lane.lifecycle_state = data.lifecycle_state or lane.lifecycle_state
            lane.queue_depth = data.queue_depth
            lane.active_since = (
                data.occurred_at
                if data.lifecycle_state == "ACTIVE" and not was_active
                else lane.active_since
            )
            if data.event_type == "handoff":
                lane.last_handoff_at = data.occurred_at
            lane.last_event_at, lane.updated_at, lane.version = (
                data.occurred_at,
                utc_now(),
                lane.version + 1,
            )
        await session.flush()
        return event, False

    async def overview(
        self, session: AsyncSession, *, company_id: UUID, now: datetime | None = None
    ) -> tuple[
        FactoryRoadmap,
        list[FactoryControlEvent],
        list[FactoryLaneState],
        dict,
        datetime,
    ]:
        generated = now or utc_now()
        roadmap = self.roadmap()
        events = list(
            (
                await session.scalars(
                    select(FactoryControlEvent).where(
                        FactoryControlEvent.company_id == company_id
                    )
                )
            ).all()
        )
        lanes = list(
            (
                await session.scalars(
                    select(FactoryLaneState)
                    .where(FactoryLaneState.company_id == company_id)
                    .order_by(FactoryLaneState.lane_code)
                )
            ).all()
        )
        return (
            roadmap,
            events,
            lanes,
            calculate_metrics(
                roadmap=roadmap, events=events, lanes=lanes, now=generated
            ),
            generated,
        )

    async def capture_snapshot(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        actor_user_id: UUID,
        snapshot_key: str,
        now: datetime | None = None,
    ) -> tuple[FactoryControlSnapshot, bool]:
        await self._lock_identity(
            session,
            company_id=company_id,
            namespace="snapshot",
            key=snapshot_key,
        )
        existing = await session.scalar(
            select(FactoryControlSnapshot).where(
                FactoryControlSnapshot.company_id == company_id,
                FactoryControlSnapshot.snapshot_key == snapshot_key,
            )
        )
        if existing is not None:
            return existing, True
        roadmap, _, lanes, metrics, captured = await self.overview(
            session, company_id=company_id, now=now
        )
        snapshot = FactoryControlSnapshot(
            company_id=company_id,
            snapshot_key=snapshot_key,
            roadmap_digest=roadmap.digest,
            metrics=metrics,
            lane_states=[
                {
                    "lane_code": lane.lane_code,
                    "milestone_code": lane.milestone_code,
                    "lifecycle_state": lane.lifecycle_state,
                    "queue_depth": lane.queue_depth,
                }
                for lane in lanes
            ],
            captured_at=captured,
            created_by_user_id=actor_user_id,
        )
        session.add(snapshot)
        await session.flush()
        return snapshot, False


factory_control_service = FactoryControlService()
