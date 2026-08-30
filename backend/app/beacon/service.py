from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.beacon.contracts import BeaconFactRepository
from app.beacon.evaluation import SignalEvaluationService, signal_evaluation_service
from app.beacon.operational_prioritization import (
    OperationalAttentionQueue,
    OperationalSignalPrioritizer,
    operational_signal_prioritizer,
)
from app.beacon.records import BeaconAttentionQueue, BeaconSignal
from app.beacon.repository import (
    BeaconLifecycleRepository,
    beacon_fact_repository,
    beacon_lifecycle_repository,
)
from app.platform.permissions.authorization import (
    AuthorizationContext,
    authorization_service,
)
from app.platform.permissions.codes import AnalyticsPermission

SIGNAL_TTL = timedelta(minutes=15)


class BeaconQueryService:
    """Orchestrates read-only facts, rule evaluation, and lifecycle projection."""

    def __init__(
        self,
        repository: BeaconFactRepository = beacon_fact_repository,
        lifecycle_repository: BeaconLifecycleRepository = beacon_lifecycle_repository,
        evaluation_service: SignalEvaluationService = signal_evaluation_service,
        operational_prioritizer: OperationalSignalPrioritizer = operational_signal_prioritizer,
    ) -> None:
        self.repository = repository
        self.lifecycle_repository = lifecycle_repository
        self.evaluation_service = evaluation_service
        self.operational_prioritizer = operational_prioritizer

    async def get_operational_attention_queue(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        now: datetime | None = None,
    ) -> OperationalAttentionQueue:
        evaluated_at = now or datetime.now(timezone.utc)
        queue = await self.get_attention_queue(
            session, context=context, now=evaluated_at
        )
        return self.operational_prioritizer.prioritize(
            queue.active,
            company_id=context.company.id,
            branch_id=context.active_branch.id if context.active_branch else None,
            evaluated_at=evaluated_at,
        )

    async def list_signals(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        now: datetime | None = None,
    ) -> tuple[BeaconSignal, ...]:
        return (
            await self.get_attention_queue(session, context=context, now=now)
        ).active

    async def get_attention_queue(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        now: datetime | None = None,
    ) -> BeaconAttentionQueue:
        authorization_service.require_permission(context, AnalyticsPermission.READ)
        evaluated_at = now or datetime.now(timezone.utc)
        signals = await self.evaluate_current(
            session,
            company_id=context.company.id,
            branch_ids=(
                frozenset({context.active_branch.id})
                if context.active_branch is not None
                else context.authorized_branch_ids
            ),
            measured_at=evaluated_at,
        )
        latest = await self.lifecycle_repository.latest_for_conditions(
            session,
            company_id=context.company.id,
            condition_keys=tuple(signal.condition_key for signal in signals),
        )
        projected = tuple(
            self.evaluation_service.project_lifecycle(
                signal,
                latest.get(signal.condition_key),
                evaluated_at,
            )
            for signal in signals
        )
        return BeaconAttentionQueue(
            active=tuple(
                signal
                for signal in projected
                if not signal.lifecycle.temporarily_suppressed
            ),
            snoozed=tuple(
                signal
                for signal in projected
                if signal.lifecycle.temporarily_suppressed
            ),
        )

    async def evaluate_current(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_ids: frozenset[UUID],
        measured_at: datetime,
    ) -> tuple[BeaconSignal, ...]:
        snapshot = await self.repository.load_snapshot(
            session,
            company_id=company_id,
            branch_ids=branch_ids,
            measured_at=measured_at,
        )
        return self.evaluation_service.evaluate_signals(snapshot)


beacon_query_service = BeaconQueryService()
