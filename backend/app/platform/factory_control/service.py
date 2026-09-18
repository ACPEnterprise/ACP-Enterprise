from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import fmean
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering_execution.controlled.models import ControlledExecutionOfferModel
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
from app.worker_control.models import EngineeringWorker

SOURCE_ROADMAP_PATH = (
    Path(__file__).resolve().parents[4] / "docs/factory/acp_full_system_roadmap.yaml"
)
PACKAGED_ROADMAP_PATH = Path(__file__).with_name("data") / "roadmap.json"
PACKAGED_ROADMAP_DIGEST_PATH = PACKAGED_ROADMAP_PATH.with_suffix(".sha256")
STAGES = ("engineering_complete", "beta_complete", "owner_accepted", "closed")


class FactoryEventConflict(RuntimeError):
    pass


class FactoryEvidenceError(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def percent(numerator: float, denominator: float) -> float:
    return round(100 * numerator / denominator, 2) if denominator else 0.0


def evidence_digest(value: dict) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def calculate_metrics(
    *,
    roadmap: FactoryRoadmap,
    events: list[FactoryControlEvent],
    lanes: list[FactoryLaneState],
    now: datetime,
) -> dict:
    roadmap_codes = {item.code for item in roadmap.milestones}
    superseded_codes = {
        code
        for milestone in roadmap.milestones
        for code in milestone.supersedes
        if code in roadmap_codes
    }
    represented = tuple(
        milestone
        for milestone in roadmap.milestones
        if milestone.code not in superseded_codes
    )
    represented_codes = {item.code for item in represented}
    milestone_stages: dict[str, set[str]] = defaultdict(set)
    for milestone in represented:
        if milestone.engineering_status in {
            "ENGINEERING_READY",
            "INTEGRATED",
            "DEPLOYED_BETA",
            "CLOSED",
        }:
            milestone_stages[milestone.code].add("engineering_complete")
        # DEPLOYED_BETA alone is not proof of operator usability.  The stricter
        # Beta score advances from a beta_complete event or a CLOSED roadmap
        # milestone, never merely from a deployment label.
        if milestone.beta_deployment_status == "CLOSED":
            milestone_stages[milestone.code].add("beta_complete")
        if milestone.owner_acceptance_status in {"ACCEPTED", "CLOSED"}:
            milestone_stages[milestone.code].add("owner_accepted")
        if milestone.lifecycle_status == "CLOSED":
            milestone_stages[milestone.code].update(STAGES)
    defect_state: dict[str, bool] = {}
    defects_discovered = defects_closed = defects_reopened = 0
    gate_state: dict[str, bool] = {}
    handoffs: dict[str, tuple[datetime, str | None]] = {}
    pickup_latencies: list[float] = []
    domain_pickup_latencies: list[float] = []
    release_pickup_latencies: list[float] = []
    integrations: dict[str, datetime] = {}
    release_latencies: list[float] = []
    closed_event_times: dict[str, datetime] = {}
    rework = first_pass = 0
    for event in sorted(events, key=lambda item: (item.occurred_at, str(item.id))):
        milestone_code = event.milestone_code
        if milestone_code in represented_codes:
            stages = milestone_stages[milestone_code]
            if event.event_type == "engineering_complete":
                stages.add("engineering_complete")
            elif event.event_type == "beta_complete":
                stages.update(("engineering_complete", "beta_complete"))
            elif event.event_type == "owner_accepted":
                stages.update(
                    ("engineering_complete", "beta_complete", "owner_accepted")
                )
            elif event.event_type == "closed":
                stages.update(STAGES)
                closed_event_times[milestone_code] = event.occurred_at
            elif event.event_type == "engineering_reopened":
                stages.difference_update(STAGES)
                closed_event_times.pop(milestone_code, None)
            elif event.event_type == "beta_reopened":
                stages.difference_update(
                    ("beta_complete", "owner_accepted", "closed")
                )
                closed_event_times.pop(milestone_code, None)
            elif event.event_type == "owner_acceptance_reopened":
                stages.difference_update(("owner_accepted", "closed"))
                closed_event_times.pop(milestone_code, None)
            elif event.event_type == "milestone_reopened":
                stages.discard("closed")
                closed_event_times.pop(milestone_code, None)
        identity = str(event.details.get("defect_id", event.milestone_code or event.id))
        if event.event_type == "defect_opened":
            if identity not in defect_state:
                defects_discovered += 1
            elif defect_state[identity] is False:
                defects_reopened += 1
            defect_state[identity] = True
        elif event.event_type == "defect_closed":
            if defect_state.get(identity) is True:
                defects_closed += 1
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
            handoffs[handoff_key] = (
                event.occurred_at,
                getattr(event, "controlling_enterprise", None),
            )
        elif event.event_type == "pickup" and handoff_key in handoffs:
            handoff_at, handoff_controller = handoffs.pop(handoff_key)
            latency = max(0.0, (event.occurred_at - handoff_at).total_seconds())
            pickup_latencies.append(latency)
            controller = getattr(event, "controlling_enterprise", None)
            controller = controller or handoff_controller
            if controller in {"OM2E", "LaptopE"}:
                domain_pickup_latencies.append(latency)
            elif controller == "OM1E":
                release_pickup_latencies.append(latency)
        elif event.event_type == "integration":
            integrations[handoff_key] = event.occurred_at
        elif event.event_type == "release" and handoff_key in integrations:
            release_latencies.append(
                max(
                    0.0,
                    (event.occurred_at - integrations.pop(handoff_key)).total_seconds(),
                )
            )
        elif event.event_type == "rework_started":
            rework += 1
        elif event.event_type == "first_pass_complete":
            first_pass += 1
    total = len(represented)
    completed_times = closed_event_times.values()
    rates = {
        days: percent(
            sum(stamp >= now - timedelta(days=days) for stamp in completed_times), total
        )
        for days in (1, 3, 7)
    }
    active = sum(lane.lifecycle_state.upper() == "ACTIVE" for lane in lanes)
    assigned = sum(lane.lifecycle_state.upper() == "ASSIGNED" for lane in lanes)
    eligible_states = {"ACTIVE", "ASSIGNED", "ELIGIBLE_IDLE", "WAITING_INTEGRATION"}
    eligible = sum(lane.lifecycle_state.upper() in eligible_states for lane in lanes)
    eligible_idle_seconds = sum(
        max(
            0.0,
            (
                now
                - cast(datetime, getattr(lane, "eligible_idle_since", now))
            ).total_seconds(),
        )
        for lane in lanes
        if lane.lifecycle_state.upper() == "ELIGIBLE_IDLE"
        and getattr(lane, "eligible_idle_since", None) is not None
    )
    completed = sum("closed" in stages for stages in milestone_stages.values())
    attempts = first_pass + rework
    oldest = min(value[0] for value in handoffs.values()) if handoffs else None
    engineering_count = sum(
        "engineering_complete" in stages for stages in milestone_stages.values()
    )
    beta_count = sum(
        "beta_complete" in stages for stages in milestone_stages.values()
    )
    owner_count = sum(
        "owner_accepted" in stages for stages in milestone_stages.values()
    )
    human_gated = sum(
        milestone.owner_acceptance_status
        in {"HUMAN_GATE", "OWNER_ACCEPTANCE_REQUIRED"}
        and "closed" not in milestone_stages[milestone.code]
        for milestone in represented
    )
    provider_gated = sum(
        milestone.owner_acceptance_status == "PROVIDER_GATE"
        and "closed" not in milestone_stages[milestone.code]
        for milestone in represented
    )
    return {
        "represented_milestones": total,
        "superseded_milestones": len(superseded_codes),
        "engineering_count": engineering_count,
        "beta_count": beta_count,
        "owner_count": owner_count,
        "closed_count": completed,
        "engineering_percent": percent(engineering_count, total),
        "beta_percent": percent(beta_count, total),
        "owner_percent": percent(owner_count, total),
        "closed_percent": percent(completed, total),
        "engineering_remaining_weight": total - engineering_count,
        "human_gated_remaining_weight": human_gated,
        "provider_gated_remaining_weight": provider_gated,
        "weighted_delivery_percent": round(
            0.5 * rates[1] + 0.3 * rates[3] + 0.2 * rates[7], 2
        ),
        "delivery_1d_percent": rates[1],
        "delivery_3d_percent": rates[3],
        "delivery_7d_percent": rates[7],
        "open_defects": sum(defect_state.values()),
        "defects_discovered": defects_discovered,
        "defects_closed": defects_closed,
        "defects_reopened": defects_reopened,
        "open_gates": sum(gate_state.values()),
        "utilization_percent": percent(active, len(lanes)),
        "effective_utilization_percent": percent(active + assigned, eligible),
        "eligible_idle_seconds": round(eligible_idle_seconds, 2),
        "pickup_latency_seconds": round(fmean(pickup_latencies), 2)
        if pickup_latencies
        else None,
        "domain_pickup_latency_seconds": round(fmean(domain_pickup_latencies), 2)
        if domain_pickup_latencies
        else None,
        "release_pickup_latency_seconds": round(fmean(release_pickup_latencies), 2)
        if release_pickup_latencies
        else None,
        "release_latency_seconds": round(fmean(release_latencies), 2)
        if release_latencies
        else None,
        "queue_depth": sum(lane.queue_depth for lane in lanes),
        "oldest_handoff_seconds": round((now - oldest).total_seconds(), 2)
        if oldest
        else None,
        "rework_rate_percent": percent(rework, attempts),
        "first_pass_yield_percent": percent(first_pass, attempts),
        "event_history_status": "MEASURED" if events else "NOT_YET_MEASURED",
        "lane_history_status": "MEASURED" if lanes else "NOT_YET_MEASURED",
        "velocity_history_status": (
            "MEASURED" if closed_event_times else "NOT_YET_MEASURED"
        ),
    }


class FactoryControlService:
    @staticmethod
    async def _lock_identity(
        session: AsyncSession, *, namespace: str, key: str
    ) -> None:
        identity = f"factory-control:{namespace}:{key}"
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
        controller_worker_identity_id: UUID,
        controller_tenant_company_id: UUID,
        data: FactoryEventIn,
    ) -> tuple[FactoryControlEvent, bool]:
        if (
            data.tenant_company_id is not None
            and data.tenant_company_id != controller_tenant_company_id
        ):
            raise FactoryEvidenceError(
                "controller cannot attribute evidence to another tenant"
            )
        details = safe_event_details(data.details)
        request_digest = evidence_digest(
            {
                "tenant_company_id": str(data.tenant_company_id)
                if data.tenant_company_id
                else None,
                "lane_code": data.lane_code,
                "milestone_code": data.milestone_code,
                "event_type": data.event_type,
                "lifecycle_state": data.lifecycle_state,
                "queue_depth": data.queue_depth,
                "machine": data.machine,
                "current_assignment": data.current_assignment,
                "next_queued_item": data.next_queued_item,
                "controlling_enterprise": data.controlling_enterprise,
                "self_refill_health": data.self_refill_health,
                "occurred_at": data.occurred_at.isoformat(),
                "details": details,
                "controller_worker_identity_id": str(controller_worker_identity_id),
            }
        )
        await self._lock_identity(
            session,
            namespace="event",
            key=data.idempotency_key,
        )
        existing = await session.scalar(
            select(FactoryControlEvent).where(
                FactoryControlEvent.idempotency_key == data.idempotency_key,
            )
        )
        if existing is not None:
            if existing.request_digest != request_digest:
                raise FactoryEventConflict(
                    "factory event idempotency key was reused with different facts"
                )
            return existing, True
        # Distinct keys for a lane serialize too. This closes the absent-row race
        # and makes equal timestamps deterministic by idempotency key.
        await self._lock_identity(session, namespace="lane", key=data.lane_code)
        lane = await session.scalar(
            select(FactoryLaneState)
            .where(FactoryLaneState.lane_code == data.lane_code)
            .with_for_update()
        )
        event = FactoryControlEvent(
            tenant_company_id=data.tenant_company_id,
            lane_code=data.lane_code,
            milestone_code=data.milestone_code,
            event_type=data.event_type,
            lifecycle_state=data.lifecycle_state,
            queue_depth=data.queue_depth,
            machine=data.machine,
            current_assignment=data.current_assignment,
            next_queued_item=data.next_queued_item,
            controlling_enterprise=data.controlling_enterprise,
            self_refill_health=data.self_refill_health,
            source="development_factory_controller",
            idempotency_key=data.idempotency_key,
            request_digest=request_digest,
            details=details,
            controller_worker_identity_id=controller_worker_identity_id,
            occurred_at=data.occurred_at,
            received_at=utc_now(),
        )
        session.add(event)
        await session.flush()
        if lane is None:
            lane = FactoryLaneState(
                lane_code=data.lane_code,
                milestone_code=data.milestone_code,
                lifecycle_state=data.lifecycle_state or "ELIGIBLE_IDLE",
                queue_depth=data.queue_depth,
                machine=data.machine,
                current_assignment=data.current_assignment,
                next_queued_item=data.next_queued_item,
                controlling_enterprise=data.controlling_enterprise,
                self_refill_health=data.self_refill_health,
                active_since=data.occurred_at
                if data.lifecycle_state == "ACTIVE"
                else None,
                eligible_idle_since=data.occurred_at
                if data.lifecycle_state == "ELIGIBLE_IDLE"
                else None,
                last_handoff_at=data.occurred_at
                if data.event_type == "handoff"
                else None,
                last_event_at=data.occurred_at,
                last_event_id=event.id,
                last_event_key=data.idempotency_key,
                updated_at=utc_now(),
            )
            session.add(lane)
        elif (data.occurred_at, data.idempotency_key) >= (
            lane.last_event_at,
            lane.last_event_key,
        ):
            was_active = lane.lifecycle_state.upper() == "ACTIVE"
            was_eligible_idle = lane.lifecycle_state.upper() == "ELIGIBLE_IDLE"
            lane.milestone_code = data.milestone_code
            lane.lifecycle_state = data.lifecycle_state or lane.lifecycle_state
            lane.queue_depth = data.queue_depth
            lane.machine = data.machine
            lane.current_assignment = data.current_assignment
            lane.next_queued_item = data.next_queued_item
            lane.controlling_enterprise = data.controlling_enterprise
            lane.self_refill_health = data.self_refill_health
            lane.active_since = (
                data.occurred_at
                if data.lifecycle_state == "ACTIVE" and not was_active
                else lane.active_since
            )
            if data.lifecycle_state == "ELIGIBLE_IDLE":
                if not was_eligible_idle:
                    lane.eligible_idle_since = data.occurred_at
            else:
                lane.eligible_idle_since = None
            if data.event_type == "handoff":
                lane.last_handoff_at = data.occurred_at
            lane.last_event_at, lane.updated_at, lane.version = (
                data.occurred_at,
                utc_now(),
                lane.version + 1,
            )
            lane.last_event_id = event.id
            lane.last_event_key = data.idempotency_key
        await session.flush()
        return event, False

    async def overview(
        self, session: AsyncSession, *, now: datetime | None = None
    ) -> tuple[
        FactoryRoadmap,
        list[FactoryControlEvent],
        list[FactoryLaneState],
        dict,
        datetime,
    ]:
        generated = now or utc_now()
        roadmap = self.roadmap()
        events = list((await session.scalars(select(FactoryControlEvent))).all())
        lanes = list(
            (
                await session.scalars(
                    select(FactoryLaneState).order_by(FactoryLaneState.lane_code)
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
        controller_worker_identity_id: UUID,
        controller_tenant_company_id: UUID,
        snapshot_key: str,
        captured_at: datetime,
        tenant_company_id: UUID | None = None,
    ) -> tuple[FactoryControlSnapshot, bool]:
        if (
            tenant_company_id is not None
            and tenant_company_id != controller_tenant_company_id
        ):
            raise FactoryEvidenceError(
                "controller cannot attribute evidence to another tenant"
            )
        request_digest = evidence_digest(
            {
                "snapshot_key": snapshot_key,
                "tenant_company_id": str(tenant_company_id)
                if tenant_company_id
                else None,
                "captured_at": captured_at.isoformat(),
                "controller_worker_identity_id": str(controller_worker_identity_id),
            }
        )
        await self._lock_identity(
            session,
            namespace="snapshot",
            key=snapshot_key,
        )
        existing = await session.scalar(
            select(FactoryControlSnapshot).where(
                FactoryControlSnapshot.snapshot_key == snapshot_key,
            )
        )
        if existing is not None:
            if existing.request_digest != request_digest:
                raise FactoryEventConflict(
                    "factory snapshot key was reused with different facts"
                )
            return existing, True
        roadmap, _, lanes, metrics, captured = await self.overview(
            session, now=captured_at
        )
        snapshot = FactoryControlSnapshot(
            tenant_company_id=tenant_company_id,
            snapshot_key=snapshot_key,
            request_digest=request_digest,
            roadmap_digest=roadmap.digest,
            metrics=metrics,
            lane_states=[
                {
                    "lane_code": lane.lane_code,
                    "milestone_code": lane.milestone_code,
                    "lifecycle_state": lane.lifecycle_state,
                    "queue_depth": lane.queue_depth,
                    "machine": lane.machine,
                    "current_assignment": lane.current_assignment,
                    "next_queued_item": lane.next_queued_item,
                    "controlling_enterprise": lane.controlling_enterprise,
                    "self_refill_health": lane.self_refill_health,
                }
                for lane in lanes
            ],
            captured_at=captured,
            created_by_worker_identity_id=controller_worker_identity_id,
        )
        session.add(snapshot)
        await session.flush()
        return snapshot, False

    async def sync_controller_lane(
        self,
        session: AsyncSession,
        *,
        controller_worker_identity_id: UUID,
        controller_worker_id: UUID,
        controller_tenant_company_id: UUID,
    ) -> tuple[FactoryControlEvent, bool]:
        """Project existing Development Factory truth; do not accept asserted state."""
        worker = await session.scalar(
            select(EngineeringWorker).where(
                EngineeringWorker.id == controller_worker_id,
                EngineeringWorker.company_id == controller_tenant_company_id,
            )
        )
        if worker is None:
            raise FactoryEvidenceError("controller worker evidence is unavailable")
        queue_depth = int(
            await session.scalar(
                select(func.count(ControlledExecutionOfferModel.id)).where(
                    ControlledExecutionOfferModel.company_id
                    == controller_tenant_company_id,
                    ControlledExecutionOfferModel.state == "available",
                )
            )
            or 0
        )
        active_offer = await session.scalar(
            select(ControlledExecutionOfferModel)
            .where(
                ControlledExecutionOfferModel.company_id
                == controller_tenant_company_id,
                ControlledExecutionOfferModel.worker_id == worker.id,
                ControlledExecutionOfferModel.state == "acquired",
            )
            .order_by(
                ControlledExecutionOfferModel.acquired_at,
                ControlledExecutionOfferModel.id,
            )
        )
        next_offer = await session.scalar(
            select(ControlledExecutionOfferModel)
            .where(
                ControlledExecutionOfferModel.company_id
                == controller_tenant_company_id,
                ControlledExecutionOfferModel.state == "available",
            )
            .order_by(
                ControlledExecutionOfferModel.created_at,
                ControlledExecutionOfferModel.id,
            )
        )
        state = cast(
            Literal[
                "ACTIVE",
                "ASSIGNED",
                "ELIGIBLE_IDLE",
                "DEPENDENCY_BLOCKED",
                "UNSAFE_STOP",
            ],
            {
                "registered": "ASSIGNED",
                "available": "ELIGIBLE_IDLE",
                "leased": "ACTIVE",
                "offline": "UNSAFE_STOP",
                "disabled": "DEPENDENCY_BLOCKED",
            }[worker.lifecycle_state],
        )
        source_digest = evidence_digest(
            {
                "worker_id": str(worker.id),
                "company_id": str(worker.company_id),
                "name": worker.name,
                "lifecycle_state": worker.lifecycle_state,
                "version": worker.version,
                "updated_at": worker.updated_at.isoformat(),
                "queue_depth": queue_depth,
                "current_assignment": str(active_offer.command_id)
                if active_offer
                else None,
                "next_queued_item": str(next_offer.command_id) if next_offer else None,
            }
        )
        controlling_enterprise = cast(
            Literal["OM1E", "OM2E", "LaptopE"] | None,
            "OM1E"
            if worker.name.upper().startswith("OM1")
            else "OM2E"
            if worker.name.upper().startswith("OM2")
            else "LaptopE"
            if worker.name.upper().startswith(("LAPTOP", "PHONE"))
            else None,
        )
        self_refill_health = cast(
            Literal[
                "SELF_REFILL_HEALTHY",
                "ELIGIBLE_IDLE",
                "DEPENDENCY_BLOCKED",
                "UNSAFE_STOP",
                "UNKNOWN",
            ],
            {
                "registered": "UNKNOWN",
                "available": "ELIGIBLE_IDLE",
                "leased": "SELF_REFILL_HEALTHY",
                "offline": "UNSAFE_STOP",
                "disabled": "DEPENDENCY_BLOCKED",
            }[worker.lifecycle_state],
        )
        return await self.ingest(
            session,
            controller_worker_identity_id=controller_worker_identity_id,
            controller_tenant_company_id=controller_tenant_company_id,
            data=FactoryEventIn(
                tenant_company_id=controller_tenant_company_id,
                lane_code=worker.name,
                event_type="controller_sync",
                lifecycle_state=state,
                queue_depth=queue_depth,
                machine=worker.provider_identifier,
                current_assignment=str(active_offer.command_id)
                if active_offer
                else None,
                next_queued_item=str(next_offer.command_id) if next_offer else None,
                controlling_enterprise=controlling_enterprise,
                self_refill_health=self_refill_health,
                idempotency_key=(
                    f"development-factory-worker:{worker.id}:version:{worker.version}:"
                    f"queue:{queue_depth}"
                ),
                occurred_at=worker.updated_at,
                details={
                    "source_kind": "engineering_worker",
                    "source_id": str(worker.id),
                    "digest": source_digest,
                    "status": worker.lifecycle_state,
                    "count": queue_depth,
                },
            ),
        )


factory_control_service = FactoryControlService()
