from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.beacon.contracts import BeaconLifecycleAction
from app.beacon.errors import (
    BeaconSignalNotFoundError,
    BeaconSignalStaleError,
    BeaconSnoozeInvalidError,
)
from app.beacon.records import BeaconLifecycleEvent
from app.beacon.repository import (
    BeaconLifecycleRepository,
    beacon_lifecycle_repository,
)
from app.beacon.service import BeaconQueryService, beacon_query_service
from app.platform.permissions.authorization import (
    AuthorizationContext,
    authorization_service,
)
from app.platform.permissions.codes import AnalyticsPermission, BeaconPermission


@dataclass(frozen=True)
class RecordBeaconLifecycleAction:
    signal_id: UUID
    evidence_digest: str
    action: BeaconLifecycleAction
    snooze_until: datetime | None = None


class BeaconLifecycleService:
    def __init__(
        self,
        *,
        repository: BeaconLifecycleRepository = beacon_lifecycle_repository,
        query_service: BeaconQueryService = beacon_query_service,
    ) -> None:
        self.repository = repository
        self.query_service = query_service

    async def record(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: RecordBeaconLifecycleAction,
        now: datetime | None = None,
    ) -> BeaconLifecycleEvent:
        authorization_service.require_permission(context, BeaconPermission.REVIEW)
        occurred_at = now or datetime.now(timezone.utc)
        self._validate_command(command, occurred_at)
        async with session.begin():
            signals = await self.query_service.evaluate_current(
                session,
                company_id=context.company.id,
                measured_at=occurred_at,
            )
            signal = next(
                (item for item in signals if item.id == command.signal_id),
                None,
            )
            if signal is None:
                raise BeaconSignalNotFoundError(
                    "The current Company signal was not found."
                )
            if signal.evidence_digest != command.evidence_digest:
                raise BeaconSignalStaleError(
                    "Signal evidence changed and must be reviewed again."
                )
            return await self.repository.append(
                session,
                company_id=context.company.id,
                condition_key=signal.condition_key,
                signal_id=signal.id,
                rule_code=signal.rule_code,
                signal_source=signal.source,
                evidence_digest=signal.evidence_digest,
                action=command.action,
                actor_membership_id=context.membership.id,
                action_at=occurred_at,
                snooze_until=command.snooze_until,
            )

    async def history(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        condition_key: UUID,
        limit: int,
    ) -> tuple[BeaconLifecycleEvent, ...]:
        authorization_service.require_permission(context, AnalyticsPermission.READ)
        return await self.repository.list_history(
            session,
            company_id=context.company.id,
            condition_key=condition_key,
            limit=limit,
        )

    @staticmethod
    def _validate_command(
        command: RecordBeaconLifecycleAction,
        occurred_at: datetime,
    ) -> None:
        if len(command.evidence_digest) != 64:
            raise BeaconSignalStaleError("Signal evidence digest is invalid.")
        if command.action is BeaconLifecycleAction.SNOOZE:
            if (
                command.snooze_until is None
                or command.snooze_until.tzinfo is None
                or command.snooze_until <= occurred_at
            ):
                raise BeaconSnoozeInvalidError(
                    "Snooze requires an explicit future timestamp."
                )
        elif command.snooze_until is not None:
            raise BeaconSnoozeInvalidError(
                "Only a snooze action may include snooze_until."
            )


beacon_lifecycle_service = BeaconLifecycleService()
