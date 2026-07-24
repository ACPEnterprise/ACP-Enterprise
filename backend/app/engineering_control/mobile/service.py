from datetime import datetime, timezone
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
from app.engineering_control.service import EngineeringControlService
from app.platform.permissions.authorization import AuthorizationContext

from .schemas import MobileCommandDetail, MobileCommandPage, MobileCommandSummary


class MobileEngineeringControlService:
    """Owner-review projection over the authoritative Engineering Control service."""

    def __init__(self, control: EngineeringControlService | None = None) -> None:
        self.control = control or EngineeringControlService()

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


mobile_engineering_control_service = MobileEngineeringControlService()
