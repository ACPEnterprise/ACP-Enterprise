from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from math import ceil
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering_control.commands import (
    ApproveEngineeringCommand,
    CancelEngineeringCommand,
    EngineeringCommandQuery,
)
from app.engineering_control.records import (
    EngineeringApprovalState,
    EngineeringCommandRecord,
)
from app.engineering_control.review.contracts import EngineeringReviewState
from app.engineering_control.review.service import EngineeringReviewService
from app.engineering_control.service import EngineeringControlService
from app.platform.permissions.authorization import AuthorizationContext

from .repository import MobileConnectivityRepository
from .schemas import (
    MobileCommandDetail,
    MobileCommandPage,
    MobileCommandSummary,
    MobileEngineeringConnectivity,
    MobileOwnerReviewPage,
    MobileOwnerReviewSummary,
)

HEARTBEAT_FRESH_FOR = timedelta(seconds=90)


class MobileEngineeringControlService:
    """Owner-review projection over the authoritative Engineering Control service."""

    def __init__(
        self,
        control: EngineeringControlService | None = None,
        reviews: EngineeringReviewService | None = None,
        connectivity: type[MobileConnectivityRepository] = MobileConnectivityRepository,
    ) -> None:
        self.control = control or EngineeringControlService()
        self.reviews = reviews or EngineeringReviewService()
        self.connectivity = connectivity

    async def list_owner_reviews(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        page: int,
        page_size: int,
        now: datetime | None = None,
    ) -> MobileOwnerReviewPage:
        current = now or datetime.now(timezone.utc)
        packages, total = await self.reviews.list_packages(
            session,
            context=context,
            state=EngineeringReviewState.PENDING,
            page=page,
            page_size=page_size,
        )
        source = await self.connectivity.load(
            session,
            company_id=context.company.id,
            now=current,
        )
        if source is None:
            connection = MobileEngineeringConnectivity(
                state="disconnected",
                session_id=None,
                last_contact_at=None,
                heartbeat_at=None,
            )
        else:
            last_contact = max(
                timestamp
                for timestamp in (
                    source.established_at,
                    source.last_message_at,
                    source.heartbeat_at,
                )
                if timestamp is not None
            )
            connection = MobileEngineeringConnectivity(
                state=self._connectivity_state(
                    heartbeat_at=source.heartbeat_at,
                    now=current,
                ),
                session_id=source.session_id,
                last_contact_at=last_contact,
                heartbeat_at=source.heartbeat_at,
            )
        return MobileOwnerReviewPage(
            items=tuple(
                MobileOwnerReviewSummary(
                    id=package.review.id,
                    command_id=package.review.command_id,
                    execution_id=package.review.execution_id,
                    ecid=package.ecid,
                    provider_identifier=package.review.provider_identifier,
                    result_status=package.result_status,
                    result_disposition=package.result_disposition,
                    validation_summary=dict(package.validation_summary),
                    file_boundary=self._file_boundary(package.validation_summary),
                    state=package.review.state,
                    created_at=package.review.created_at,
                    decision=(
                        package.decision.decision
                        if package.decision is not None
                        else None
                    ),
                    decided_at=(
                        package.decision.decided_at
                        if package.decision is not None
                        else None
                    ),
                )
                for package in packages
            ),
            connectivity=connection,
            page=page,
            page_size=page_size,
            total_count=total,
            total_pages=ceil(total / page_size) if total else 0,
        )

    @staticmethod
    def _connectivity_state(*, heartbeat_at: datetime | None, now: datetime) -> str:
        if heartbeat_at is None:
            return "connecting"
        if now - heartbeat_at <= HEARTBEAT_FRESH_FOR:
            return "connected"
        return "disconnected"

    async def list_pending(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        page: int,
        page_size: int,
    ) -> MobileCommandPage:
        result = await self.control.list_commands(
            session,
            context=context,
            query=EngineeringCommandQuery(
                approval_state=EngineeringApprovalState.AWAITING_APPROVAL,
                page=page,
                page_size=page_size,
            ),
        )
        return MobileCommandPage(
            items=tuple(
                MobileCommandSummary.model_validate(item) for item in result.items
            ),
            page=result.page,
            page_size=result.page_size,
            total_count=result.total_count,
            total_pages=result.total_pages,
        )

    async def detail(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command_id: UUID,
        now: datetime | None = None,
    ) -> MobileCommandDetail:
        record = await self.control.get_command(
            session, context=context, command_id=command_id
        )
        return self._detail(record, now=now)

    async def approve(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: ApproveEngineeringCommand,
    ) -> MobileCommandDetail:
        return self._detail(
            await self.control.approve_command(
                session, context=context, command=command
            )
        )

    async def cancel(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: CancelEngineeringCommand,
    ) -> MobileCommandDetail:
        return self._detail(
            await self.control.cancel_command(session, context=context, command=command)
        )

    @staticmethod
    def _detail(
        record: EngineeringCommandRecord, *, now: datetime | None = None
    ) -> MobileCommandDetail:
        current_time = now or datetime.now(timezone.utc)
        pending = (
            record.approval_state is EngineeringApprovalState.AWAITING_APPROVAL
            and record.expires_at > current_time
        )
        cancellable = record.approval_state in {
            EngineeringApprovalState.AWAITING_APPROVAL,
            EngineeringApprovalState.APPROVED,
        }
        return MobileCommandDetail.model_validate(
            {
                **{
                    field: getattr(record, field)
                    for field in MobileCommandDetail.model_fields
                    if hasattr(record, field)
                },
                "can_approve": pending,
                "can_cancel": cancellable,
                "execution_connected": False,
            }
        )

    @staticmethod
    def _file_boundary(summary: object) -> tuple[str, ...]:
        if not isinstance(summary, Mapping):
            return ()
        value = summary.get("file_boundary")
        if not isinstance(value, list) or not all(
            isinstance(path, str) for path in value
        ):
            return ()
        return tuple(value)


mobile_engineering_control_service = MobileEngineeringControlService()
