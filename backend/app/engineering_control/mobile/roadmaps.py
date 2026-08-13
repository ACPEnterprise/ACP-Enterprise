from datetime import datetime, timedelta, timezone
from typing import ClassVar
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.engineering_control.commands import (
    ApproveEngineeringCommand,
    CreateEngineeringCommand,
)
from app.engineering_control.repository_operation.models import (
    EngineeringRepositoryOperation,
)
from app.engineering_control.revision_evidence import compose_revision_instruction
from app.engineering_control.scheduler.manifest import ExecutionBoundaryDefinition
from app.engineering_control.service import EngineeringControlService
from app.engineering_control.workstream_runtime import EngineeringWorkstreamEvent
from app.engineering_execution.controlled.models import ControlledExecutionResultModel
from app.engineering_execution.models import EngineeringExecution
from app.platform.permissions.authorization import AuthorizationContext

from .control import EngineeringWorkstreamControl
from .service import MobileEngineeringControlService


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def validate_candidate_execution_head(
    *, requested_code_changes: bool, candidate_head: str, authoritative_head: str
) -> None:
    if requested_code_changes and candidate_head != authoritative_head:
        raise ValueError(
            "The milestone execution base is stale; scheduler reconciliation is required."
        )


class EngineeringRoadmap(Base):
    __tablename__ = "engineering_roadmaps"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','completed','archived')",
            name="ck_engineering_roadmap_status",
        ),
        CheckConstraint("version >= 1", name="ck_engineering_roadmap_version"),
        CheckConstraint(
            "expected_head ~ '^[0-9a-f]{40}$'", name="ck_engineering_roadmap_head"
        ),
        Index(
            "ix_engineering_roadmap_company_status",
            "company_id",
            "status",
            "updated_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    repository_key: Mapped[str] = mapped_column(String(100), nullable=False)
    expected_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    expected_head: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class EngineeringMilestone(Base):
    __tablename__ = "engineering_milestones"
    __table_args__ = (
        UniqueConstraint(
            "roadmap_id", "position", name="uq_engineering_milestone_position"
        ),
        UniqueConstraint(
            "company_id", "milestone_code", name="uq_engineering_milestone_code"
        ),
        CheckConstraint("position >= 1", name="ck_engineering_milestone_position"),
        CheckConstraint("version >= 1", name="ck_engineering_milestone_version"),
        CheckConstraint(
            "status IN ('draft','planned','ready','running','externally_running','waiting_review','waiting_approval','blocked','completed','paused','cancelled','skipped','archived')",
            name="ck_engineering_milestone_status",
        ),
        CheckConstraint(
            "reconciliation_state IN ('current','legacy_unreconciled','superseded','ambiguous','reconciliation_required')",
            name="ck_engineering_milestone_reconciliation_state",
        ),
        Index(
            "ix_engineering_milestone_company_status",
            "company_id",
            "status",
            "updated_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    roadmap_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("engineering_roadmaps.id", ondelete="RESTRICT"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    milestone_code: Mapped[str | None] = mapped_column(String(80))
    scheduler_version: Mapped[str | None] = mapped_column(String(80))
    scheduler_fingerprint: Mapped[str | None] = mapped_column(String(64))
    permanent_capacity_identity: Mapped[str | None] = mapped_column(String(8))
    implementation_classification: Mapped[str | None] = mapped_column(String(16))
    integration_checkpoint: Mapped[str | None] = mapped_column(String(80))
    starting_commit_rule: Mapped[str | None] = mapped_column(Text)
    starting_commit_evidence: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    migration_classification: Mapped[str | None] = mapped_column(String(32))
    shared_contract_classification: Mapped[str | None] = mapped_column(String(32))
    readiness_state: Mapped[str | None] = mapped_column(String(32))
    dependency_evidence: Mapped[list[object]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    reconciliation_state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="legacy_unreconciled"
    )
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    owning_workstream: Mapped[str] = mapped_column(String(100), nullable=False)
    owning_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    authority: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    constraints: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    dependencies: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    validation: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    deliverables: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    stop_conditions: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    expected_completion_evidence: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    definition_approved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    requested_code_changes: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    externally_adoptable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    external_evidence: Mapped[str | None] = mapped_column(Text)
    command_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("engineering_commands.id", ondelete="RESTRICT")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class EngineeringMilestoneEvent(Base):
    __tablename__ = "engineering_milestone_events"
    __table_args__ = (
        Index(
            "ix_engineering_milestone_event_order",
            "company_id",
            "occurred_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    roadmap_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("engineering_roadmaps.id", ondelete="RESTRICT"),
        nullable=False,
    )
    milestone_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("engineering_milestones.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    prior_status: Mapped[str | None] = mapped_column(String(24))
    new_status: Mapped[str] = mapped_column(String(24), nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    reason: Mapped[str | None] = mapped_column(String(240))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class RoadmapService:
    actionable: ClassVar[frozenset[str]] = frozenset(
        {"ready", "waiting_review", "waiting_approval"}
    )

    def __init__(self) -> None:
        self.commands = EngineeringControlService()
        self.mobile = MobileEngineeringControlService()

    async def create(
        self, db: AsyncSession, *, context: AuthorizationContext, payload: object
    ) -> EngineeringRoadmap:
        from .schemas import RoadmapCreate

        data = (
            payload
            if isinstance(payload, RoadmapCreate)
            else RoadmapCreate.model_validate(payload)
        )
        now = utc_now()
        roadmap = EngineeringRoadmap(
            company_id=context.company.id,
            title=data.title,
            repository_key=data.repository_key,
            expected_branch=data.expected_branch,
            expected_head=data.expected_head,
            status="active",
            created_at=now,
            updated_at=now,
        )
        async with db.begin():
            db.add(roadmap)
            await db.flush()
            for index, definition in enumerate(data.milestones, start=1):
                status = "planned"
                if index == 1:
                    status = "ready" if definition.approved else "waiting_approval"
                milestone = EngineeringMilestone(
                    company_id=context.company.id,
                    roadmap_id=roadmap.id,
                    position=index,
                    title=definition.title,
                    objective=definition.objective,
                    owning_workstream=definition.owning_workstream or data.title,
                    owning_branch=definition.owning_branch or data.expected_branch,
                    authority=list(definition.authority),
                    constraints=list(definition.constraints),
                    dependencies=list(definition.dependencies),
                    validation=list(definition.validation),
                    deliverables=list(definition.deliverables),
                    stop_conditions=list(definition.stop_conditions),
                    expected_completion_evidence=list(
                        definition.expected_completion_evidence
                    ),
                    status=status,
                    definition_approved=definition.approved,
                    requested_code_changes=definition.requested_code_changes,
                    created_at=now,
                    updated_at=now,
                )
                db.add(milestone)
                await db.flush()
                self._event(
                    db,
                    milestone,
                    None,
                    status,
                    context.user.id,
                    "milestone_created",
                    None,
                    now,
                )
        return roadmap

    async def list(
        self, db: AsyncSession, *, context: AuthorizationContext
    ) -> tuple[EngineeringRoadmap, ...]:
        await self.reconcile(db, context=context)
        return tuple(
            (
                await db.scalars(
                    select(EngineeringRoadmap)
                    .where(EngineeringRoadmap.company_id == context.company.id)
                    .order_by(EngineeringRoadmap.updated_at.desc())
                )
            ).all()
        )

    async def milestones(
        self,
        db: AsyncSession,
        *,
        context: AuthorizationContext,
        roadmap_id: UUID | None = None,
        actionable_only: bool = False,
    ) -> tuple[EngineeringMilestone, ...]:
        await self.reconcile(db, context=context)
        query = select(EngineeringMilestone).where(
            EngineeringMilestone.company_id == context.company.id
        )
        if roadmap_id:
            query = query.where(EngineeringMilestone.roadmap_id == roadmap_id)
        if actionable_only:
            query = query.where(EngineeringMilestone.status.in_(self.actionable))
        return tuple(
            (
                await db.scalars(
                    query.order_by(
                        EngineeringMilestone.updated_at.desc(),
                        EngineeringMilestone.position,
                    )
                )
            ).all()
        )

    async def action(
        self,
        db: AsyncSession,
        *,
        context: AuthorizationContext,
        milestone_id: UUID,
        action: str,
        expected_version: int,
        reason: str | None,
    ) -> EngineeringMilestone:
        now = utc_now()
        milestone = await self._get(db, context.company.id, milestone_id)
        if milestone.version != expected_version:
            raise ValueError("Milestone version is stale.")
        current_status = milestone.status
        definition_approved = milestone.definition_approved
        roadmap_id = milestone.roadmap_id
        command_id = milestone.command_id
        requested_code_changes = milestone.requested_code_changes
        milestone_validation = tuple(str(item) for item in milestone.validation)
        owning_workstream = milestone.owning_workstream
        milestone_code = milestone.milestone_code
        starting_commit_evidence = dict(milestone.starting_commit_evidence)
        reconciliation_state = milestone.reconciliation_state
        readiness_state = milestone.readiness_state
        instruction = self._instruction(milestone)
        await db.rollback()
        if action == "request_revision" and command_id is not None:
            if (
                current_status not in {"running", "blocked", "waiting_review"}
                or not definition_approved
                or reconciliation_state != "current"
                or readiness_state != "ready"
            ):
                raise ValueError(
                    "Request Revision requires a current, approved failed milestone."
                )
            prior_execution = await db.scalar(
                select(EngineeringExecution).where(
                    EngineeringExecution.company_id == context.company.id,
                    EngineeringExecution.command_id == command_id,
                    EngineeringExecution.state == "failed",
                )
            )
            if prior_execution is None:
                raise ValueError(
                    "Request Revision requires a terminal failed execution."
                )
            validation_runs = prior_execution.evidence_summary.get(
                "validation_runs", []
            )
            if not isinstance(validation_runs, list) or not validation_runs:
                raise ValueError(
                    "Request Revision requires durable validation diagnostics."
                )
            failure_classification = prior_execution.failure_classification
            if not failure_classification:
                raise ValueError("Request Revision requires a failure classification.")
            prior_execution_id = prior_execution.id
            changed_paths = prior_execution.evidence_summary.get("file_boundary", [])
            if not isinstance(changed_paths, list):
                changed_paths = []
            instruction = compose_revision_instruction(
                milestone_instruction=instruction,
                prior_execution_id=str(prior_execution_id),
                failure_classification=failure_classification,
                implementation_summary=str(
                    prior_execution.evidence_summary.get("implementation_summary", "")
                )
                or None,
                changed_paths=tuple(str(path) for path in changed_paths),
                validation_runs=tuple(
                    item for item in validation_runs if isinstance(item, dict)
                ),
            )
            await db.rollback()
            return await self._start_command(
                db,
                context=context,
                milestone_id=milestone_id,
                expected_version=expected_version,
                current_status=current_status,
                roadmap_id=roadmap_id,
                requested_code_changes=requested_code_changes,
                milestone_validation=milestone_validation,
                owning_workstream=owning_workstream,
                milestone_code=milestone_code,
                starting_commit_evidence=starting_commit_evidence,
                instruction=instruction,
                action=action,
                reason=reason or f"revision_of:{prior_execution_id}",
                revision_of_execution_id=prior_execution_id,
                now=now,
            )
        if action == "start":
            if current_status != "ready" or not definition_approved:
                raise ValueError("Only an approved ready milestone can start.")
            if reconciliation_state != "current":
                raise ValueError(
                    "Only a scheduler-current milestone can start; reconciliation is required."
                )
            if readiness_state != "ready":
                raise ValueError(
                    "The durable scheduler has not authorized this milestone to start."
                )
            from .external_adoption import (
                ACTIVE_ADOPTIONS,
                ExternalMilestoneAdoption,
            )

            active_external = await db.scalar(
                select(ExternalMilestoneAdoption.id).where(
                    ExternalMilestoneAdoption.company_id == context.company.id,
                    ExternalMilestoneAdoption.roadmap_id == roadmap_id,
                    ExternalMilestoneAdoption.status.in_(ACTIVE_ADOPTIONS),
                )
            )
            if active_external is not None:
                raise ValueError(
                    "An adopted external milestone still owns this roadmap scope."
                )
            roadmap = await self._roadmap(db, context.company.id, roadmap_id)
            repository_key = roadmap.repository_key
            expected_branch = roadmap.expected_branch
            expected_head = roadmap.expected_head
            candidate_head = str(starting_commit_evidence.get("authoritative_head", ""))
            validate_candidate_execution_head(
                requested_code_changes=requested_code_changes,
                candidate_head=candidate_head,
                authoritative_head=expected_head,
            )
            if requested_code_changes:
                from app.engineering_control.repository_readiness import (
                    repository_readiness_service,
                )

                if not await repository_readiness_service.is_current_for_milestone(
                    db,
                    company_id=context.company.id,
                    milestone_id=milestone_id,
                    repository_key=repository_key,
                    branch=expected_branch,
                    candidate_head=expected_head,
                    evidence=starting_commit_evidence,
                    now=now,
                ):
                    raise ValueError(
                        "The assigned provider repository is not prepared for the current execution base."
                    )
            await db.rollback()
            return await self._start_command(
                db,
                context=context,
                milestone_id=milestone_id,
                expected_version=expected_version,
                current_status=current_status,
                roadmap_id=roadmap_id,
                requested_code_changes=requested_code_changes,
                milestone_validation=milestone_validation,
                owning_workstream=owning_workstream,
                milestone_code=milestone_code,
                starting_commit_evidence=starting_commit_evidence,
                instruction=instruction,
                action=action,
                reason=reason,
                revision_of_execution_id=None,
                now=now,
            )

        transitions = {
            "approve": ({"waiting_review", "waiting_approval"}, "completed"),
            "reject": ({"waiting_review", "waiting_approval"}, "blocked"),
            "skip": ({"planned", "ready", "waiting_approval", "blocked"}, "skipped"),
            "archive": ({"completed", "cancelled", "skipped", "blocked"}, "archived"),
            "pause": ({"running"}, "paused"),
            "resume": ({"paused"}, "running"),
            "cancel": ({"ready", "running", "paused", "blocked"}, "cancelled"),
        }
        if action not in transitions:
            raise ValueError("Unsupported milestone action.")
        allowed, target = transitions[action]
        if current_status not in allowed:
            raise ValueError(f"Milestone cannot {action} from {current_status}.")
        if action == "approve" and current_status == "waiting_approval":
            target = "planned"
        if action in {"pause", "resume", "cancel"} and command_id:
            await self.mobile.control_workstream(
                db,
                context=context,
                command_id=command_id,
                action=action,
                reason=reason or f"milestone_{action}",
                now=now,
            )
        async with db.begin():
            locked = await self._get(db, context.company.id, milestone_id, lock=True)
            if locked.version != expected_version or locked.status != current_status:
                raise ValueError("Milestone changed before the action completed.")
            if action == "approve" and locked.status == "waiting_approval":
                locked.definition_approved = True
            self._transition(db, locked, target, context.user.id, action, reason, now)
            await self._emit_realtime_event(db, locked, action, now)
            await self._promote(
                db, context.company.id, locked.roadmap_id, now, context.user.id
            )
            await db.flush()
        return locked

    async def _start_command(
        self,
        db: AsyncSession,
        *,
        context: AuthorizationContext,
        milestone_id: UUID,
        expected_version: int,
        current_status: str,
        roadmap_id: UUID,
        requested_code_changes: bool,
        milestone_validation: tuple[str, ...],
        owning_workstream: str,
        milestone_code: str | None,
        starting_commit_evidence: dict[str, object],
        instruction: str,
        action: str,
        reason: str | None,
        revision_of_execution_id: UUID | None,
        now: datetime,
    ) -> EngineeringMilestone:
        roadmap = await self._roadmap(db, context.company.id, roadmap_id)
        repository_key = roadmap.repository_key
        expected_branch = roadmap.expected_branch
        expected_head = roadmap.expected_head
        candidate_head = str(starting_commit_evidence.get("authoritative_head", ""))
        validate_candidate_execution_head(
            requested_code_changes=requested_code_changes,
            candidate_head=candidate_head,
            authoritative_head=expected_head,
        )
        if requested_code_changes:
            from app.engineering_control.repository_readiness import (
                repository_readiness_service,
            )

            if not await repository_readiness_service.is_current_for_milestone(
                db,
                company_id=context.company.id,
                milestone_id=milestone_id,
                repository_key=repository_key,
                branch=expected_branch,
                candidate_head=expected_head,
                evidence=starting_commit_evidence,
                now=now,
            ):
                raise ValueError(
                    "The assigned provider repository is not prepared for the current execution base."
                )
        await db.rollback()
        command = await self.commands.create_command(
            db,
            context=context,
            command=CreateEngineeringCommand(
                command_type="mission_control_milestone",
                owner_instruction=instruction,
                repository_key=repository_key,
                expected_branch=expected_branch,
                expected_head=expected_head,
                requested_code_changes=requested_code_changes,
                expires_at=now + timedelta(days=7),
                idempotency_key=(
                    f"milestone:{milestone_id}:v{expected_version}:{action}:"
                    f"{revision_of_execution_id or 'initial'}"
                ),
                execution_boundary=self._execution_boundary(
                    repository_key=repository_key,
                    expected_branch=expected_branch,
                    expected_head=expected_head,
                    milestone_code=milestone_code,
                    owning_workstream=owning_workstream,
                    starting_commit_evidence=starting_commit_evidence,
                    validation=milestone_validation,
                    requested_code_changes=requested_code_changes,
                ),
            ),
        )
        command = await self.commands.approve_command(
            db,
            context=context,
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
        )
        await self.mobile.control_workstream(
            db,
            context=context,
            command_id=command.id,
            action="start",
            reason="mission_control_dispatch",
            now=now,
        )
        async with db.begin():
            locked = await self._get(db, context.company.id, milestone_id, lock=True)
            if locked.version != expected_version or locked.status != current_status:
                raise ValueError("Milestone changed before dispatch completed.")
            locked.command_id = command.id
            self._transition(
                db, locked, "running", context.user.id, action, reason, now
            )
            await db.flush()
            return locked

    @staticmethod
    async def _emit_realtime_event(
        db: AsyncSession,
        milestone: EngineeringMilestone,
        action: str,
        now: datetime,
    ) -> None:
        if milestone.command_id is None:
            return
        control = await db.scalar(
            select(EngineeringWorkstreamControl).where(
                EngineeringWorkstreamControl.company_id == milestone.company_id,
                EngineeringWorkstreamControl.command_id == milestone.command_id,
            )
        )
        if control is None:
            return
        runtime_state = {
            "planned": "queued",
            "ready": "queued",
            "running": "running",
            "externally_running": "running",
            "draft": "queued",
            "paused": "paused",
            "waiting_review": "waiting_for_owner",
            "waiting_approval": "waiting_for_owner",
            "blocked": "failed",
            "completed": "completed",
            "cancelled": "cancelled",
            "skipped": "cancelled",
            "archived": "completed",
        }[milestone.status]
        db.add(
            EngineeringWorkstreamEvent(
                company_id=milestone.company_id,
                command_id=milestone.command_id,
                control_id=control.id,
                control_version=control.version,
                event_type="milestone_action",
                action=action,
                runtime_state=runtime_state,
                reason_code=f"milestone_{action}",
                idempotency_key=(
                    f"milestone:{milestone.id}:version:{milestone.version}:action:{action}"
                ),
                occurred_at=now,
            )
        )

    async def reconcile(
        self, db: AsyncSession, *, context: AuthorizationContext
    ) -> None:
        from app.engineering_control.workstream_runtime import (
            EngineeringWorkstreamRuntime,
        )

        candidates = tuple(
            (
                await db.scalars(
                    select(EngineeringMilestone).where(
                        EngineeringMilestone.company_id == context.company.id,
                        EngineeringMilestone.status == "running",
                        EngineeringMilestone.command_id.is_not(None),
                    )
                )
            ).all()
        )
        changes: list[tuple[UUID, str, str | None]] = []
        for milestone in candidates:
            runtime = await db.scalar(
                select(EngineeringWorkstreamRuntime).where(
                    EngineeringWorkstreamRuntime.company_id == context.company.id,
                    EngineeringWorkstreamRuntime.command_id == milestone.command_id,
                )
            )
            if runtime and runtime.runtime_state == "completed":
                resulting_head = await db.scalar(
                    select(EngineeringRepositoryOperation.resulting_commit_sha)
                    .where(
                        EngineeringRepositoryOperation.company_id == context.company.id,
                        EngineeringRepositoryOperation.command_id
                        == milestone.command_id,
                        EngineeringRepositoryOperation.state == "succeeded",
                    )
                    .order_by(EngineeringRepositoryOperation.succeeded_at.desc())
                    .limit(1)
                )
                if resulting_head is None:
                    controlled_result = await db.scalar(
                        select(ControlledExecutionResultModel)
                        .where(
                            ControlledExecutionResultModel.company_id
                            == context.company.id,
                            ControlledExecutionResultModel.command_id
                            == milestone.command_id,
                            ControlledExecutionResultModel.outcome == "succeeded",
                        )
                        .order_by(ControlledExecutionResultModel.completed_at.desc())
                        .limit(1)
                    )
                    if controlled_result is not None:
                        candidate = controlled_result.output.get("published_commit_sha")
                        if isinstance(candidate, str) and len(candidate) == 40:
                            resulting_head = candidate
                changes.append((milestone.id, "waiting_review", resulting_head))
            elif runtime and runtime.runtime_state in {"failed", "cancelled"}:
                changes.append(
                    (
                        milestone.id,
                        "blocked" if runtime.runtime_state == "failed" else "cancelled",
                        None,
                    )
                )
        if not changes:
            return
        now = utc_now()
        await db.rollback()
        async with db.begin():
            for milestone_id, target, resulting_head in changes:
                locked = await self._get(
                    db, context.company.id, milestone_id, lock=True
                )
                if locked.status == "running":
                    self._transition(
                        db, locked, target, None, "runtime_reconciled", None, now
                    )
                    if resulting_head is not None:
                        roadmap = await self._roadmap(
                            db, context.company.id, locked.roadmap_id
                        )
                        roadmap.expected_head = resulting_head
                        roadmap.version += 1
                        roadmap.updated_at = now

    async def _promote(
        self,
        db: AsyncSession,
        company_id: UUID,
        roadmap_id: UUID,
        now: datetime,
        actor: UUID,
    ) -> EngineeringMilestone | None:
        active = await db.scalar(
            select(EngineeringMilestone.id).where(
                EngineeringMilestone.company_id == company_id,
                EngineeringMilestone.roadmap_id == roadmap_id,
                EngineeringMilestone.status.in_(
                    {
                        "ready",
                        "running",
                        "externally_running",
                        "paused",
                        "waiting_review",
                    }
                ),
            )
        )
        if active:
            return None
        next_item = await db.scalar(
            select(EngineeringMilestone)
            .where(
                EngineeringMilestone.company_id == company_id,
                EngineeringMilestone.roadmap_id == roadmap_id,
                EngineeringMilestone.status == "planned",
            )
            .order_by(EngineeringMilestone.position)
            .with_for_update()
        )
        if next_item:
            self._transition(
                db,
                next_item,
                "ready" if next_item.definition_approved else "waiting_approval",
                actor,
                "roadmap_progression",
                None,
                now,
            )
            return next_item
        roadmap = await self._roadmap(db, company_id, roadmap_id)
        roadmap.status = "completed"
        roadmap.version += 1
        roadmap.updated_at = now
        return None

    @staticmethod
    def _instruction(item: EngineeringMilestone) -> str:
        sections = [
            ("Objective", [item.objective]),
            ("Owning workstream", [item.owning_workstream]),
            ("Owning branch", [item.owning_branch]),
            ("Authority", item.authority),
            ("Constraints", item.constraints),
            ("Dependencies", item.dependencies),
            ("Validation", item.validation),
            ("Deliverables", item.deliverables),
            ("Stop conditions", item.stop_conditions),
            ("Expected completion evidence", item.expected_completion_evidence),
        ]
        body = [f"# {item.title}"]
        for heading, values in sections:
            body.extend([f"\n## {heading}", *[f"- {value}" for value in values]])
        return "\n".join(body)

    @staticmethod
    def _execution_boundary(
        *,
        repository_key: str,
        expected_branch: str,
        expected_head: str,
        milestone_code: str | None,
        owning_workstream: str,
        starting_commit_evidence: dict[str, object],
        validation: tuple[str, ...],
        requested_code_changes: bool,
    ) -> dict[str, object]:
        explicit = starting_commit_evidence.get("execution_boundary")
        if explicit is not None:
            if milestone_code is None:
                raise ValueError(
                    "This milestone boundary has no durable milestone identity."
                )
            try:
                definition = ExecutionBoundaryDefinition.model_validate(explicit)
            except ValidationError as error:
                raise ValueError(
                    "This milestone has an invalid machine-enforceable boundary."
                ) from error
            if definition.boundary_id != milestone_code:
                raise ValueError(
                    "This milestone boundary does not match the durable milestone identity."
                )
            return {
                "allowed_repository": repository_key,
                "allowed_branch": expected_branch,
                "expected_head": expected_head,
                "allowed_paths": list(definition.allowed_paths),
                "forbidden_paths": list(definition.forbidden_paths),
                "permitted_operations": list(definition.permitted_operations),
                "validation_requirements": list(definition.validation_requirements),
            }

        name = owning_workstream.casefold()
        roots = {
            "beacon": ("backend/app/beacon/**", "backend/tests/beacon/**", "docs/**"),
            "operations": (
                "backend/app/scheduling/**",
                "backend/tests/scheduling/**",
                "docs/**",
            ),
            "business economics": (
                "backend/app/business_economics/**",
                "backend/tests/business_economics/**",
                "docs/**",
            ),
            "customer migration": (
                "backend/app/operational_migration/**",
                "backend/tests/operational_migration/**",
                "docs/**",
            ),
            "mission control": (
                "backend/app/engineering_control/**",
                "backend/app/engineering_execution/**",
                "backend/tests/engineering_control/**",
                "backend/tests/engineering_execution/**",
                "frontend/src/features/engineering-control/**",
                "docs/**",
            ),
        }
        allowed = next((paths for key, paths in roots.items() if key in name), None)
        if allowed is None and not requested_code_changes:
            allowed = ("**",)
        if allowed is None:
            raise ValueError(
                "This milestone has no approved machine-enforceable path boundary."
            )
        operations = ["inspect", "validate"]
        if requested_code_changes:
            operations.extend(("modify", "commit", "mechanical_reconcile", "push"))
        normalized_validation = ["git diff --check"]
        for item in validation:
            lowered = item.casefold()
            for token, command in (
                ("ruff", "ruff"),
                ("mypy", "mypy"),
                ("pytest", "pytest"),
                ("test", "pytest"),
                ("eslint", "eslint"),
                ("typescript", "typescript"),
                ("production build", "typescript"),
            ):
                if token in lowered and command not in normalized_validation:
                    normalized_validation.append(command)
        return {
            "allowed_repository": repository_key,
            "allowed_branch": expected_branch,
            "expected_head": expected_head,
            "allowed_paths": list(allowed),
            "forbidden_paths": [
                ".git/**",
                ".env*",
                "**/.env*",
                "**/*credential*",
                "**/*private-key*",
                "**/node_modules/**",
                "**/__pycache__/**",
            ],
            "permitted_operations": operations,
            "validation_requirements": normalized_validation,
        }

    @staticmethod
    def _transition(
        db: AsyncSession,
        item: EngineeringMilestone,
        target: str,
        actor: UUID | None,
        event: str,
        reason: str | None,
        now: datetime,
    ) -> None:
        prior = item.status
        item.status = target
        item.version += 1
        item.updated_at = now
        if target == "running":
            item.started_at = now
        if target in {"completed", "skipped", "cancelled"}:
            item.completed_at = now
        if target == "completed":
            item.reviewed_at = now
        RoadmapService._event(db, item, prior, target, actor, event, reason, now)

    @staticmethod
    def _event(
        db: AsyncSession,
        item: EngineeringMilestone,
        prior: str | None,
        target: str,
        actor: UUID | None,
        event: str,
        reason: str | None,
        now: datetime,
    ) -> None:
        db.add(
            EngineeringMilestoneEvent(
                company_id=item.company_id,
                roadmap_id=item.roadmap_id,
                milestone_id=item.id,
                event_type=event,
                prior_status=prior,
                new_status=target,
                actor_user_id=actor,
                reason=reason,
                occurred_at=now,
            )
        )

    @staticmethod
    async def _get(
        db: AsyncSession, company_id: UUID, milestone_id: UUID, lock: bool = False
    ) -> EngineeringMilestone:
        query = select(EngineeringMilestone).where(
            EngineeringMilestone.company_id == company_id,
            EngineeringMilestone.id == milestone_id,
        )
        item = await db.scalar(query.with_for_update() if lock else query)
        if item is None:
            raise LookupError("Milestone was not found.")
        return item

    @staticmethod
    async def _roadmap(
        db: AsyncSession, company_id: UUID, roadmap_id: UUID
    ) -> EngineeringRoadmap:
        item = await db.scalar(
            select(EngineeringRoadmap).where(
                EngineeringRoadmap.company_id == company_id,
                EngineeringRoadmap.id == roadmap_id,
            )
        )
        if item is None:
            raise LookupError("Roadmap was not found.")
        return item


roadmap_service = RoadmapService()
