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
from app.engineering_execution.status.schemas import MobileExecutionStatus
from app.engineering_execution.status.service import MobileExecutionStatusService
from app.platform.permissions.authorization import AuthorizationContext

from .repository import MobileConnectivityRepository
from .schemas import (
    MobileCommandDetail,
    MobileCommandPage,
    MobileCommandSummary,
    MobileEngineeringConnectivity,
    MobileOwnerReviewPage,
    MobileOwnerReviewSummary,
    MobileWorkstreamPage,
    MobileWorkstreamSummary,
)

HEARTBEAT_FRESH_FOR = timedelta(seconds=90)


class MobileEngineeringControlService:
    """Owner-review projection over the authoritative Engineering Control service."""

    def __init__(
        self,
        control: EngineeringControlService | None = None,
        reviews: EngineeringReviewService | None = None,
        statuses: MobileExecutionStatusService | None = None,
        connectivity: type[MobileConnectivityRepository] = MobileConnectivityRepository,
    ) -> None:
        self.control = control or EngineeringControlService()
        self.reviews = reviews or EngineeringReviewService()
        self.statuses = statuses or MobileExecutionStatusService()
        self.connectivity = connectivity

    async def list_workstreams(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        page: int,
        page_size: int,
        now: datetime | None = None,
    ) -> MobileWorkstreamPage:
        current = now or datetime.now(timezone.utc)
        commands = await self.control.list_commands(
            session,
            context=context,
            query=EngineeringCommandQuery(page=page, page_size=page_size),
        )
        items: list[MobileWorkstreamSummary] = []
        for command in commands.items:
            status = await self.statuses.get(
                session,
                context=context,
                command_id=command.id,
                now=current,
            )
            items.append(self._workstream_summary(command=command, status=status))
        return MobileWorkstreamPage(
            items=tuple(items),
            connectivity=await self._connectivity(
                session, company_id=context.company.id, now=current
            ),
            page=commands.page,
            page_size=commands.page_size,
            total_count=commands.total_count,
            total_pages=commands.total_pages,
        )

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
        connection = await self._connectivity(
            session, company_id=context.company.id, now=current
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
                    file_boundary=self._file_boundary(
                        package.validation_summary,
                        package.evidence_summary,
                    ),
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

    async def _connectivity(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        now: datetime,
    ) -> MobileEngineeringConnectivity:
        source = await self.connectivity.load(session, company_id=company_id, now=now)
        if source is None:
            return MobileEngineeringConnectivity(
                state="disconnected",
                session_id=None,
                last_contact_at=None,
                heartbeat_at=None,
            )
        last_contact = max(
            timestamp
            for timestamp in (
                source.established_at,
                source.last_message_at,
                source.heartbeat_at,
            )
            if timestamp is not None
        )
        return MobileEngineeringConnectivity(
            state=self._connectivity_state(heartbeat_at=source.heartbeat_at, now=now),
            session_id=source.session_id,
            last_contact_at=last_contact,
            heartbeat_at=source.heartbeat_at,
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
    def _file_boundary(*summaries: object) -> tuple[str, ...]:
        for summary in summaries:
            if not isinstance(summary, Mapping):
                continue
            value = summary.get("file_boundary")
            if isinstance(value, (list, tuple)) and all(
                isinstance(path, str) for path in value
            ):
                return tuple(value)
        return ()

    @classmethod
    def _workstream_summary(
        cls,
        *,
        command: EngineeringCommandRecord,
        status: MobileExecutionStatus,
    ) -> MobileWorkstreamSummary:
        lifecycle, next_action, owner_action = cls._next_action(
            command=command, status=status
        )
        failure = (
            status.repository_operation_failure_classification
            or status.result.failure_classification
        )
        repository_clean = (
            True
            if status.repository_operation_status == "succeeded"
            and status.repository_operation_resulting_commit_sha is not None
            else None
        )
        return MobileWorkstreamSummary(
            command_id=command.id,
            ecid=command.ecid,
            repository_key=command.repository_key,
            expected_branch=command.expected_branch,
            expected_head=command.expected_head,
            approval_state=command.approval_state,
            lifecycle_state=lifecycle,
            progress_summary=status.progress_label,
            owner_action_required=owner_action,
            next_owner_action=next_action,
            connection_state=status.connection_state,
            assigned_worker_id=status.lease.worker_id,
            execution_id=status.execution_id,
            offer_or_lease_state=status.lease.status,
            heartbeat_at=status.heartbeat.last_seen,
            review_id=status.review_id,
            review_state=status.review_state,
            authorization_id=status.authorization_id,
            authorization_status=status.authorization_status,
            repository_operation_id=status.repository_operation_id,
            repository_operation_status=status.repository_operation_status,
            failure_classification=failure,
            resulting_commit_sha=status.repository_operation_resulting_commit_sha,
            repository_clean=repository_clean,
            owner_attention_required=(
                owner_action
                or status.repository_operation_owner_attention_required
                or failure is not None
            ),
            updated_at=status.updated_at,
        )

    @staticmethod
    def _next_action(
        *,
        command: EngineeringCommandRecord,
        status: MobileExecutionStatus,
    ) -> tuple[str, str, bool]:
        operation_state = status.repository_operation_status
        if operation_state == "reconciliation_required":
            return "reconciliation_required", "inspect_reconciliation", True
        if operation_state == "failed":
            return "failed", "inspect_repository_failure", True
        if operation_state == "succeeded":
            return "succeeded", "verify_commit", False
        if operation_state in {"requested", "reserved", "executing"}:
            return (
                "repository_operation_executing",
                "monitor_repository_operation",
                False,
            )
        if status.authorization_status == "authorized":
            return (
                "awaiting_repository_operation",
                "execute_authorized_commit",
                True,
            )
        if status.authorization_status in {"expired", "revoked"}:
            return (
                status.authorization_status,
                "review_repository_authorization",
                True,
            )
        if status.review_state == "pending":
            return "awaiting_review", "review_execution_result", True
        if (
            status.review_state == "accepted"
            and command.requested_code_changes
            and status.authorization_id is None
        ):
            return (
                "awaiting_repository_authorization",
                "authorize_repository",
                True,
            )
        if status.review_state == "rejected":
            return "revision_requested", "request_revision", True
        if status.monitoring_state == "failed":
            return "failed", "inspect_execution_failure", True
        if status.monitoring_state == "cancelled":
            return "cancelled", "none", False
        if status.monitoring_state == "completed":
            if not status.review_available:
                return "awaiting_review_package", "prepare_review_package", True
            return "completed", "none", False
        if status.monitoring_state == "running":
            return "executing", "monitor_execution", False
        if status.lease.status == "active":
            return "leased", "monitor_execution", False
        if status.monitoring_state == "queued":
            return "offered", "wait_for_worker", False
        if command.approval_state is EngineeringApprovalState.AWAITING_APPROVAL:
            return "awaiting_approval", "review_command", True
        if command.approval_state in {
            EngineeringApprovalState.CANCELED,
            EngineeringApprovalState.EXPIRED,
        }:
            return command.approval_state, "none", False
        return "waiting_for_worker", "wait_for_worker", False


mobile_engineering_control_service = MobileEngineeringControlService()
