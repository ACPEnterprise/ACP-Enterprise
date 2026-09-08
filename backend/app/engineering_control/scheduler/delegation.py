"""Fail-closed lifecycle for scoped, expiring headless queue delegation."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering_control.scheduler.approved_queue import load_approved_factory_queue
from app.engineering_control.scheduler.models import (
    EngineeringSchedulerDelegation,
    EngineeringSchedulerEvent,
)
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import (
    EngineeringCommandPermission,
    EngineeringExecutionPermission,
)

REQUIRED = frozenset(
    {
        EngineeringCommandPermission.MANAGE,
        EngineeringCommandPermission.APPROVE,
        EngineeringExecutionPermission.REQUEST,
    }
)


class SchedulerDelegationDenied(RuntimeError):
    pass


@dataclass(frozen=True)
class ActivateDelegation:
    authority_sha: str
    expires_at: datetime


class SchedulerDelegationService:
    async def activate(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        request: ActivateDelegation,
        now: datetime,
    ) -> EngineeringSchedulerDelegation:
        if not REQUIRED.issubset(context.permission_codes):
            raise SchedulerDelegationDenied(
                "all scheduler delegation permissions are required"
            )
        if request.expires_at <= now or request.expires_at > now + timedelta(hours=72):
            raise SchedulerDelegationDenied("delegation expiry must be within 72 hours")
        queue = load_approved_factory_queue()
        eligible = tuple(
            sorted(
                item.milestone_id
                for item in queue.items
                if item.execution_mode == "repository_only"
                and not item.hard_boundary_operations
            )
        )
        if not eligible:
            raise SchedulerDelegationDenied("queue has no delegable work")
        existing = await session.scalar(
            select(EngineeringSchedulerDelegation)
            .where(
                EngineeringSchedulerDelegation.company_id == context.company.id,
                EngineeringSchedulerDelegation.state == "active",
            )
            .with_for_update()
        )
        if existing is not None:
            raise SchedulerDelegationDenied("an active delegation already exists")
        row = EngineeringSchedulerDelegation(
            company_id=context.company.id,
            queue_id=queue.queue_id,
            queue_fingerprint=queue.fingerprint,
            authority_sha=request.authority_sha,
            scope={
                "non_production": True,
                "milestone_ids": eligible,
                "forbidden_operations": [
                    "production",
                    "customer_communication",
                    "money_movement",
                    "payroll_execution",
                    "autonomous_dispatch",
                ],
            },
            activated_by_user_id=context.user.id,
            credential_version=context.credential_version,
            authorization_version=context.authorization_version,
            state="active",
            activated_at=now,
            expires_at=request.expires_at,
        )
        session.add(row)
        await session.flush()
        session.add(
            EngineeringSchedulerEvent(
                company_id=context.company.id,
                event_type="delegation.activated",
                scheduler_version=queue.queue_id,
                record_id=row.id,
                actor_user_id=context.user.id,
                details={
                    "queue_fingerprint": queue.fingerprint,
                    "expires_at": request.expires_at.isoformat(),
                },
                idempotency_key=f"delegation:{row.id}:activated",
                occurred_at=now,
            )
        )
        await session.commit()
        return row

    async def require_live(
        self,
        session: AsyncSession,
        *,
        delegation_id: UUID,
        context: AuthorizationContext,
        now: datetime,
    ) -> EngineeringSchedulerDelegation:
        row = await session.scalar(
            select(EngineeringSchedulerDelegation)
            .where(EngineeringSchedulerDelegation.id == delegation_id)
            .with_for_update()
        )
        queue = load_approved_factory_queue()
        if row is None or row.state != "active" or now >= row.expires_at:
            raise SchedulerDelegationDenied("delegation is inactive or expired")
        if row.queue_id != queue.queue_id or row.queue_fingerprint != queue.fingerprint:
            raise SchedulerDelegationDenied("delegated queue identity changed")
        if (
            context.company.id != row.company_id
            or context.user.id != row.activated_by_user_id
            or context.credential_version != row.credential_version
            or context.authorization_version != row.authorization_version
            or not REQUIRED.issubset(context.permission_codes)
        ):
            raise SchedulerDelegationDenied(
                "delegating principal is no longer authorized"
            )
        return row

    async def end(
        self,
        session: AsyncSession,
        *,
        delegation_id: UUID,
        context: AuthorizationContext,
        now: datetime,
        state: str = "revoked",
        reason: str = "operator revocation",
    ) -> EngineeringSchedulerDelegation:
        if state not in {"revoked", "exhausted", "paused_p0"}:
            raise SchedulerDelegationDenied("invalid terminal state")
        row = await session.scalar(
            select(EngineeringSchedulerDelegation)
            .where(
                EngineeringSchedulerDelegation.id == delegation_id,
                EngineeringSchedulerDelegation.company_id == context.company.id,
            )
            .with_for_update()
        )
        if (
            row is None
            or row.state != "active"
            or not REQUIRED.issubset(context.permission_codes)
        ):
            raise SchedulerDelegationDenied("active delegation not found")
        row.state, row.ended_at, row.ended_by_user_id, row.end_reason = (
            state,
            now,
            context.user.id,
            reason,
        )
        session.add(
            EngineeringSchedulerEvent(
                company_id=row.company_id,
                event_type=f"delegation.{state}",
                scheduler_version=row.queue_id,
                record_id=row.id,
                actor_user_id=context.user.id,
                details={"reason": reason},
                idempotency_key=f"delegation:{row.id}:{state}",
                occurred_at=now,
            )
        )
        await session.commit()
        return row
