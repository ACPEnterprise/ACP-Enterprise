"""Authenticated application bridge for reviewed headless proposals."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering_control.commands import (
    ApproveEngineeringCommand,
    CreateEngineeringCommand,
)
from app.engineering_control.service import EngineeringControlService
from app.engineering_execution.controlled.service import ControlledExecutionService
from app.engineering_execution.service import EngineeringExecutionService
from app.platform.permissions.authorization import AuthorizationContext
from app.worker_control.contracts import AuthenticatedWorkerContext

from .approved_queue import load_approved_factory_queue
from .headless import HeadlessProposal
from .readiness import load_current_readiness_projection


class HeadlessApplicationError(RuntimeError):
    pass


class HeadlessApplicationService:
    def __init__(
        self,
        *,
        commands: EngineeringControlService | None = None,
        executions: EngineeringExecutionService | None = None,
        controlled: ControlledExecutionService | None = None,
    ) -> None:
        self.commands = commands or EngineeringControlService()
        self.executions = executions or EngineeringExecutionService()
        self.controlled = controlled or ControlledExecutionService()

    async def reconcile_stale_executions(
        self,
        session: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
        now: datetime,
    ) -> int:
        """Use the existing lease lifecycle to quarantine stale acquired work."""

        async with session.begin():
            return await self.controlled.reconcile_expired_worker_leases_in_transaction(
                session,
                worker_context=worker_context,
                now=now,
            )

    async def apply_proposal(
        self,
        session: AsyncSession,
        *,
        manage_context: AuthorizationContext,
        approve_context: AuthorizationContext,
        execution_context: AuthorizationContext,
        proposal: HeadlessProposal,
        expected_authority_sha: str,
        now: datetime,
    ) -> object:
        """Create a normal approved command and immutable execution request.

        Each underlying service independently enforces Manage, Approve, and
        Request Execution permissions. Reconciliation proposals are never
        converted into replacement executions.
        """

        if not (manage_context.company.id == approve_context.company.id == execution_context.company.id):
            raise HeadlessApplicationError("authorization contexts disagree on company")
        if proposal.kind == "reconcile":
            raise HeadlessApplicationError(
                "stale execution requires existing lease/lifecycle reconciliation"
            )
        queue = load_approved_factory_queue()
        if queue.authoritative_repository_sha != expected_authority_sha:
            raise HeadlessApplicationError("approved queue authority is stale")
        readiness = load_current_readiness_projection()
        current = next(
            (item for item in readiness.milestones if item.milestone_id == proposal.milestone_id),
            None,
        )
        work = next(
            (item for item in queue.items if item.milestone_id == proposal.milestone_id),
            None,
        )
        if current is None or work is None or current.current_state != "EXECUTABLE":
            raise HeadlessApplicationError("proposal is not currently executable")
        if work.capacity_identity != proposal.capacity_identity:
            raise HeadlessApplicationError("proposal capacity contradicts approved queue")
        command = await self.commands.create_command(
            session,
            context=manage_context,
            command=CreateEngineeringCommand(
                command_type="headless_factory_milestone",
                owner_instruction=work.instruction,
                repository_key="acp-enterprise",
                expected_branch="customer-management-v1",
                expected_head=expected_authority_sha,
                requested_code_changes=work.requested_code_changes,
                expires_at=now + timedelta(hours=72),
                idempotency_key=f"{queue.queue_id}:{work.milestone_id}:{expected_authority_sha}",
                execution_boundary={
                    "allowed_repository": "acp-enterprise",
                    "allowed_branch": "customer-management-v1",
                    "expected_head": expected_authority_sha,
                    "allowed_paths": list(work.allowed_paths),
                    "forbidden_paths": [".git/**", ".env*", "**/.env*"],
                    "permitted_operations": [
                        "inspect", "modify", "validate", "commit", "mechanical_reconcile", "push"
                    ],
                    "validation_requirements": list(work.validation_requirements),
                },
            ),
            now=now,
        )
        approved = await self.commands.approve_command(
            session,
            context=approve_context,
            command=ApproveEngineeringCommand(
                command_id=command.id,
                expected_version=command.version,
                instruction_digest=command.instruction_digest,
                request_digest=command.request_digest,
                repository_key=command.repository_key,
                expected_branch=command.expected_branch,
                expected_head=command.expected_head,
                requested_code_changes=command.requested_code_changes,
                execution_boundary_digest=command.execution_boundary_digest,
            ),
            now=now,
        )
        return await self.executions.request_execution(
            session,
            context=execution_context,
            command_id=approved.id,
            now=now,
        )


__all__ = ["HeadlessApplicationError", "HeadlessApplicationService"]
