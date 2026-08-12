from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from math import ceil
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
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
from app.engineering_control.workstream_runtime import (
    EngineeringWorkstreamEvent,
    EngineeringWorkstreamRuntime,
)
from app.engineering_execution.errors import EngineeringExecutionError
from app.engineering_execution.service import EngineeringExecutionService
from app.engineering_execution.status.schemas import MobileExecutionStatus
from app.engineering_execution.status.service import MobileExecutionStatusService
from app.platform.permissions.authorization import AuthorizationContext

from .control import WorkstreamControlRepository
from .repository import MobileConnectivityRepository
from .schemas import (
    MobileCommandDetail,
    MobileCommandPage,
    MobileCommandSummary,
    MobileEngineeringConnectivity,
    MobileOwnerReviewPage,
    MobileOwnerReviewSummary,
    MobileWorkstreamActionResult,
    MobileWorkstreamDetail,
    MobileWorkstreamPage,
    MobileWorkstreamSummary,
)

if TYPE_CHECKING:
    from .roadmaps import EngineeringMilestone

HEARTBEAT_FRESH_FOR = timedelta(seconds=90)


class MobileEngineeringControlService:
    """Owner-review projection over the authoritative Engineering Control service."""

    def __init__(
        self,
        control: EngineeringControlService | None = None,
        reviews: EngineeringReviewService | None = None,
        statuses: MobileExecutionStatusService | None = None,
        connectivity: type[MobileConnectivityRepository] = MobileConnectivityRepository,
        executions: EngineeringExecutionService | None = None,
        controls: type[WorkstreamControlRepository] = WorkstreamControlRepository,
    ) -> None:
        self.control = control or EngineeringControlService()
        self.reviews = reviews or EngineeringReviewService()
        self.statuses = statuses or MobileExecutionStatusService()
        self.connectivity = connectivity
        self.executions = executions or EngineeringExecutionService()
        self.controls = controls

    async def list_workstreams(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        page: int,
        page_size: int,
        now: datetime | None = None,
    ) -> MobileWorkstreamPage:
        from .roadmaps import EngineeringMilestone

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
            control = await self.controls.get(
                session, company_id=context.company.id, command_id=command.id
            )
            runtime = await session.scalar(
                select(EngineeringWorkstreamRuntime).where(
                    EngineeringWorkstreamRuntime.company_id == context.company.id,
                    EngineeringWorkstreamRuntime.command_id == command.id,
                )
            )
            milestone = await session.scalar(
                select(EngineeringMilestone).where(
                    EngineeringMilestone.company_id == context.company.id,
                    EngineeringMilestone.command_id == command.id,
                )
            )
            items.append(
                self._workstream_summary(
                    command=command,
                    status=status,
                    desired_state=control.desired_state if control else "active",
                    runtime=runtime,
                    milestone=milestone,
                    now=current,
                )
            )
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

    async def workstream_detail(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command_id: UUID,
        now: datetime | None = None,
    ) -> MobileWorkstreamDetail:
        from .roadmaps import EngineeringMilestone

        command = await self.control.get_command(
            session, context=context, command_id=command_id
        )
        status = await self.statuses.get(
            session, context=context, command_id=command_id, now=now
        )
        control = await self.controls.get(
            session, company_id=context.company.id, command_id=command_id
        )
        runtime = await session.scalar(
            select(EngineeringWorkstreamRuntime).where(
                EngineeringWorkstreamRuntime.company_id == context.company.id,
                EngineeringWorkstreamRuntime.command_id == command_id,
            )
        )
        milestone = await session.scalar(
            select(EngineeringMilestone).where(
                EngineeringMilestone.company_id == context.company.id,
                EngineeringMilestone.command_id == command_id,
            )
        )
        current = now or datetime.now(timezone.utc)
        summary = self._workstream_summary(
            command=command,
            status=status,
            desired_state=control.desired_state if control else "active",
            runtime=runtime,
            milestone=milestone,
            now=current,
        )
        return MobileWorkstreamDetail(
            **summary.model_dump(),
            owner_instruction=command.owner_instruction,
            requested_code_changes=command.requested_code_changes,
            created_at=command.created_at,
            started_at=status.started_at,
            finished_at=status.finished_at,
            timeline=tuple(
                {"event": item.event, "occurred_at": item.occurred_at}
                for item in status.timeline
            ),
        )

    async def control_workstream(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command_id: UUID,
        action: str,
        reason: str | None,
        now: datetime | None = None,
    ) -> MobileWorkstreamActionResult:
        occurred_at = now or datetime.now(timezone.utc)
        command = await self.control.get_command(
            session, context=context, command_id=command_id
        )
        desired = "active"
        message = "Control request accepted."
        if action == "start":
            if command.approval_state is not EngineeringApprovalState.APPROVED:
                raise ValueError("Workstream must be approved before it can start.")
            await session.rollback()
            try:
                await self.executions.request_execution(
                    session, context=context, command_id=command_id, now=occurred_at
                )
            except EngineeringExecutionError as error:
                raise ValueError(str(error)) from error
            message = "Execution request queued through the existing execution service."
        elif action == "pause":
            status = await self.statuses.get(
                session, context=context, command_id=command_id, now=occurred_at
            )
            if status.terminal:
                raise ValueError("A terminal workstream cannot be paused.")
            desired = "paused"
            message = "Pause requested; observed execution status remains authoritative until the worker acknowledges it."
        elif action == "resume":
            desired = "active"
            message = "Resume requested; the worker control plane may continue the workstream."
        elif action == "cancel":
            status = await self.statuses.get(
                session, context=context, command_id=command_id, now=occurred_at
            )
            if status.terminal:
                raise ValueError("The workstream is already terminal.")
            desired = "cancelled"
            message = "Cancellation requested; evidence and workspaces are preserved."
        else:
            raise ValueError("Unsupported workstream action.")
        record = await self.controls.set_state(
            session,
            company_id=context.company.id,
            command_id=command_id,
            actor_user_id=context.user.id,
            desired_state=desired,
            requested_action=action,
            reason=reason,
            occurred_at=occurred_at,
        )
        session.add(
            EngineeringWorkstreamEvent(
                company_id=context.company.id,
                command_id=command_id,
                control_id=record.id,
                control_version=record.version,
                worker_id=None,
                worker_session_id=None,
                event_type="owner_request",
                action=action,
                runtime_state=None,
                reason_code=reason,
                idempotency_key=f"owner:{record.id}:{record.version}",
                occurred_at=occurred_at,
            )
        )
        await session.commit()
        return MobileWorkstreamActionResult(
            command_id=command_id,
            action=action,
            desired_state=record.desired_state,
            accepted=True,
            message=message,
            updated_at=record.updated_at,
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
        desired_state: str = "active",
        runtime: EngineeringWorkstreamRuntime | None = None,
        milestone: "EngineeringMilestone | None" = None,
        now: datetime | None = None,
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
        observed_at = now or datetime.now(timezone.utc)
        pipeline = cls._pipeline_status(
            command=command,
            status=status,
            desired_state=desired_state,
            runtime=runtime,
            now=observed_at,
        )
        stale_runtime = bool(
            runtime
            and runtime.runtime_state not in {"completed", "failed", "cancelled"}
            and observed_at - runtime.heartbeat_at > timedelta(minutes=2)
        )
        if stale_runtime:
            pipeline = "reconciliation_required"
        actions = cls._available_actions(
            command=command, status=status, desired_state=desired_state
        )
        return MobileWorkstreamSummary(
            command_id=command.id,
            ecid=command.ecid,
            display_name=cls._display_name(command.owner_instruction),
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
            pipeline_status=pipeline,
            desired_state=desired_state,
            control_pending=(
                desired_state != "active" and status.monitoring_state != "cancelled"
            ),
            available_actions=actions,
            runtime_state=pipeline,
            runtime_version=runtime.version if runtime else None,
            acknowledged_action=runtime.acknowledged_action if runtime else None,
            acknowledged_at=runtime.acknowledged_at if runtime else None,
            acknowledgement_expires_at=runtime.acknowledgement_expires_at
            if runtime
            else None,
            worker_health=runtime.worker_health if runtime else None,
            progress_percent=runtime.progress_percent if runtime else None,
            current_activity=runtime.current_activity if runtime else None,
            scheduler_milestone_code=milestone.milestone_code if milestone else None,
            scheduler_version=milestone.scheduler_version if milestone else None,
            permanent_capacity_identity=(
                milestone.permanent_capacity_identity if milestone else None
            ),
            authoritative_state=cls._authoritative_state(pipeline, milestone),
            reconciliation_state=(
                milestone.reconciliation_state if milestone else "legacy_unreconciled"
            ),
            stale_runtime=stale_runtime,
        )

    @staticmethod
    def _authoritative_state(
        pipeline: str, milestone: "EngineeringMilestone | None"
    ) -> str:
        if milestone and milestone.reconciliation_state != "current":
            return "reconciliation_required"
        if pipeline == "waiting_for_owner":
            return "waiting_for_owner_review"
        if pipeline in {"acknowledged", "running", "validating", "deploying_preview"}:
            return "executing_milestone" if milestone else "active_command"
        if pipeline == "queued":
            return "waiting_for_capacity"
        if pipeline == "completed":
            return "complete"
        if pipeline in {"failed", "cancelled", "reconciliation_required", "recovering"}:
            return "reconciliation_required"
        return "active_command"

    @staticmethod
    def _display_name(owner_instruction: str) -> str:
        normalized = " ".join(owner_instruction.split()).strip(" .")
        if not normalized:
            return "Engineering workstream"
        first_sentence = normalized.split(". ", 1)[0]
        if len(first_sentence) <= 72:
            return first_sentence
        return f"{first_sentence[:69].rstrip()}…"

    @staticmethod
    def _pipeline_status(
        *,
        command: EngineeringCommandRecord,
        status: MobileExecutionStatus,
        desired_state: str,
        runtime: EngineeringWorkstreamRuntime | None,
        now: datetime,
    ) -> str:
        if (
            status.lease.status in {"active", "expired"}
            and (
                status.lease.status == "expired"
                or (
                    status.lease.expires_at is not None
                    and status.lease.expires_at <= now
                )
            )
            and status.monitoring_state not in {"completed", "failed", "cancelled"}
        ):
            return "reconciliation_required"
        if runtime is not None:
            if (
                runtime.acknowledgement_expires_at <= now
                and runtime.runtime_state not in {"completed", "failed", "cancelled"}
            ):
                return "recovering"
            return runtime.runtime_state
        if desired_state == "cancelled" or status.monitoring_state == "cancelled":
            return "cancelled"
        if (
            status.monitoring_state == "failed"
            or status.repository_operation_status
            in {"failed", "reconciliation_required"}
        ):
            return "failed"
        if status.repository_operation_status == "succeeded":
            return "completed"
        if status.repository_operation_status in {"requested", "reserved", "executing"}:
            return "deploying_preview"
        if (
            desired_state == "paused"
            or status.review_state == "pending"
            or command.approval_state is EngineeringApprovalState.AWAITING_APPROVAL
        ):
            return "waiting_for_owner"
        if status.monitoring_state == "completed":
            return "validating"
        if status.monitoring_state == "running":
            return "running"
        return "queued"

    @staticmethod
    def _available_actions(
        *,
        command: EngineeringCommandRecord,
        status: MobileExecutionStatus,
        desired_state: str,
    ) -> tuple[str, ...]:
        if status.terminal or desired_state == "cancelled":
            return ()
        actions: list[str] = []
        if (
            command.approval_state is EngineeringApprovalState.APPROVED
            and not status.execution_available
        ):
            actions.insert(0, "start")
        if desired_state == "paused":
            actions.insert(0, "resume")
        elif status.execution_available:
            actions.insert(0, "pause")
        actions.append("cancel")
        return tuple(actions)

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
