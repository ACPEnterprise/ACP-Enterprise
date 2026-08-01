import hashlib
import json
import re
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.engineering_control.models import EngineeringCommand
from app.platform.permissions.authorization import AuthorizationContext

from .roadmaps import (
    EngineeringMilestone,
    EngineeringMilestoneEvent,
    EngineeringRoadmap,
    roadmap_service,
)

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
ACTIVE_ADOPTIONS = {
    "pending_start",
    "externally_running",
    "externally_validating",
    "externally_blocked",
    "waiting_review",
    "revision_requested",
}

ALLOWED_EVIDENCE_TRANSITIONS = {
    "pending_start": {"pending_start", "externally_running", "externally_blocked"},
    "externally_running": {
        "externally_running",
        "externally_validating",
        "externally_blocked",
        "completed",
    },
    "externally_validating": {
        "externally_running",
        "externally_validating",
        "externally_blocked",
        "completed",
    },
    "externally_blocked": {
        "externally_running",
        "externally_validating",
        "externally_blocked",
    },
    "revision_requested": {
        "externally_running",
        "externally_validating",
        "externally_blocked",
        "completed",
    },
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ExternalMilestoneAdoption(Base):
    __tablename__ = "engineering_external_milestone_adoptions"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "milestone_id", name="uq_external_adoption_milestone"
        ),
        CheckConstraint("version >= 1", name="ck_external_adoption_version"),
        CheckConstraint(
            "progress_percent BETWEEN 0 AND 100",
            name="ck_external_adoption_progress",
        ),
        CheckConstraint(
            "status IN ('pending_start','externally_running','externally_validating','externally_blocked','waiting_review','revision_requested','completed','cancelled','archived')",
            name="ck_external_adoption_status",
        ),
        Index(
            "ix_external_adoption_company_status",
            "company_id",
            "status",
            "updated_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id"), nullable=False
    )
    roadmap_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("engineering_roadmaps.id"), nullable=False
    )
    milestone_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("engineering_milestones.id"), nullable=False
    )
    repository_key: Mapped[str] = mapped_column(String(100), nullable=False)
    branch: Mapped[str] = mapped_column(String(255), nullable=False)
    starting_head: Mapped[str] = mapped_column(String(40), nullable=False)
    current_head: Mapped[str] = mapped_column(String(40), nullable=False)
    worktree_identity: Mapped[str | None] = mapped_column(String(500))
    owning_external_workstream: Mapped[str] = mapped_column(String(160), nullable=False)
    declared_scope: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    protected_boundaries: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    expected_deliverables: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    validation_requirements: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    evidence_format: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_activity: Mapped[str | None] = mapped_column(String(500))
    last_evidence_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    responsible_source: Mapped[str] = mapped_column(String(160), nullable=False)
    adopted_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    adopted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    approval_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    approval_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approval_evidence_digest: Mapped[str | None] = mapped_column(String(64))
    final_head: Mapped[str | None] = mapped_column(String(40))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ExternalMilestoneEvidence(Base):
    __tablename__ = "engineering_external_milestone_evidence"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "adoption_id",
            "idempotency_key",
            name="uq_external_evidence_idempotency",
        ),
        Index(
            "ix_external_evidence_adoption_order",
            "company_id",
            "adoption_id",
            "occurred_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id"), nullable=False
    )
    adoption_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("engineering_external_milestone_adoptions.id"),
        nullable=False,
    )
    expected_adoption_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    current_activity: Mapped[str | None] = mapped_column(String(500))
    starting_head: Mapped[str] = mapped_column(String(40), nullable=False)
    current_head: Mapped[str] = mapped_column(String(40), nullable=False)
    commits: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    files_changed: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    validation_results: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    dependencies: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    blockers: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    completion_evidence: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    owner_action_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    repository_state: Mapped[str] = mapped_column(String(16), nullable=False)
    correction: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    submitted_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ExternalAdoptionError(ValueError):
    pass


class ExternalAdoptionService:
    async def adoption_for_milestone(
        self, db: AsyncSession, *, company_id: UUID, milestone_id: UUID
    ) -> ExternalMilestoneAdoption | None:
        return await db.scalar(
            select(ExternalMilestoneAdoption).where(
                ExternalMilestoneAdoption.company_id == company_id,
                ExternalMilestoneAdoption.milestone_id == milestone_id,
            )
        )

    async def list(
        self, db: AsyncSession, *, company_id: UUID
    ) -> tuple[ExternalMilestoneAdoption, ...]:
        return tuple(
            (
                await db.scalars(
                    select(ExternalMilestoneAdoption).where(
                        ExternalMilestoneAdoption.company_id == company_id
                    )
                )
            ).all()
        )

    async def latest_evidence(
        self, db: AsyncSession, *, company_id: UUID, adoption_id: UUID
    ) -> ExternalMilestoneEvidence | None:
        return await db.scalar(
            select(ExternalMilestoneEvidence)
            .where(
                ExternalMilestoneEvidence.company_id == company_id,
                ExternalMilestoneEvidence.adoption_id == adoption_id,
            )
            .order_by(ExternalMilestoneEvidence.occurred_at.desc())
            .limit(1)
        )

    async def adopt(
        self,
        db: AsyncSession,
        *,
        context: AuthorizationContext,
        milestone_id: UUID,
        payload: object,
    ) -> ExternalMilestoneAdoption:
        from .schemas import ExternalAdoptionCreate

        data = ExternalAdoptionCreate.model_validate(payload)
        now = utc_now()
        async with db.begin():
            milestone = await db.scalar(
                select(EngineeringMilestone)
                .where(
                    EngineeringMilestone.company_id == context.company.id,
                    EngineeringMilestone.id == milestone_id,
                )
                .with_for_update()
            )
            if milestone is None:
                raise LookupError("Milestone was not found.")
            roadmap = await db.get(EngineeringRoadmap, milestone.roadmap_id)
            if roadmap is None or roadmap.company_id != context.company.id:
                raise LookupError("Roadmap was not found.")
            if not milestone.externally_adoptable:
                raise ExternalAdoptionError("Milestone is not externally adoptable.")
            if milestone.command_id is not None:
                raise ExternalAdoptionError(
                    "Mission Control already dispatched this milestone."
                )
            if data.repository_key != roadmap.repository_key:
                raise ExternalAdoptionError("Repository does not match the roadmap.")
            if data.branch != milestone.owning_branch:
                raise ExternalAdoptionError("Branch does not match the milestone.")
            if not FULL_SHA.fullmatch(data.starting_head):
                raise ExternalAdoptionError("Starting HEAD is invalid.")
            if not data.starting_repository_clean:
                raise ExternalAdoptionError(
                    "Starting evidence must declare a clean repository."
                )
            conflict = await db.scalar(
                select(ExternalMilestoneAdoption.id).where(
                    ExternalMilestoneAdoption.company_id == context.company.id,
                    ExternalMilestoneAdoption.repository_key == data.repository_key,
                    ExternalMilestoneAdoption.branch == data.branch,
                    ExternalMilestoneAdoption.status.in_(ACTIVE_ADOPTIONS),
                )
            )
            if conflict is not None:
                raise ExternalAdoptionError(
                    "An active adoption already owns this repository branch."
                )
            active_adoptions = tuple(
                (
                    await db.scalars(
                        select(ExternalMilestoneAdoption).where(
                            ExternalMilestoneAdoption.company_id == context.company.id,
                            ExternalMilestoneAdoption.repository_key
                            == data.repository_key,
                            ExternalMilestoneAdoption.status.in_(ACTIVE_ADOPTIONS),
                        )
                    )
                ).all()
            )
            requested_scope = set(data.declared_scope)
            if any(
                requested_scope.intersection(item.declared_scope)
                for item in active_adoptions
            ):
                raise ExternalAdoptionError(
                    "External work overlaps an active adopted scope."
                )
            command_conflict = await db.scalar(
                select(EngineeringCommand.id).where(
                    EngineeringCommand.company_id == context.company.id,
                    EngineeringCommand.repository_key == data.repository_key,
                    EngineeringCommand.expected_branch == data.branch,
                    EngineeringCommand.execution_state.notin_(
                        {"completed", "failed", "cancelled"}
                    ),
                )
            )
            if command_conflict is not None:
                raise ExternalAdoptionError(
                    "An active Mission Control execution overlaps this branch."
                )
            adoption = ExternalMilestoneAdoption(
                company_id=context.company.id,
                roadmap_id=milestone.roadmap_id,
                milestone_id=milestone.id,
                repository_key=data.repository_key,
                branch=data.branch,
                starting_head=data.starting_head,
                current_head=data.starting_head,
                worktree_identity=data.worktree_identity,
                owning_external_workstream=data.owning_external_workstream,
                declared_scope=list(data.declared_scope),
                protected_boundaries=list(data.protected_boundaries),
                expected_deliverables=list(data.expected_deliverables),
                validation_requirements=list(data.validation_requirements),
                evidence_format=data.evidence_format,
                status="pending_start",
                progress_percent=0,
                responsible_source=data.responsible_source,
                adopted_by_user_id=context.user.id,
                adopted_at=now,
                created_at=now,
                updated_at=now,
            )
            db.add(adoption)
            milestone.external_evidence = (
                f"Adopted from {data.branch}; authenticated start evidence pending."
            )
            milestone.version += 1
            milestone.updated_at = now
            await db.flush()
            self._event(
                db,
                milestone,
                "external_adopted",
                milestone.status,
                milestone.status,
                now,
            )
            return adoption

    async def handoff(
        self,
        db: AsyncSession,
        *,
        context: AuthorizationContext,
        adoption_id: UUID,
        payload: object,
    ) -> ExternalMilestoneEvidence:
        from .schemas import ExternalEvidenceCreate

        data = ExternalEvidenceCreate.model_validate(payload)
        canonical = data.model_dump(mode="json", exclude={"evidence_digest"})
        digest = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if digest != data.evidence_digest:
            raise ExternalAdoptionError("Evidence digest is invalid.")
        now = utc_now()
        async with db.begin():
            duplicate = await db.scalar(
                select(ExternalMilestoneEvidence).where(
                    ExternalMilestoneEvidence.company_id == context.company.id,
                    ExternalMilestoneEvidence.adoption_id == adoption_id,
                    ExternalMilestoneEvidence.idempotency_key == data.idempotency_key,
                )
            )
            if duplicate is not None:
                if duplicate.evidence_digest != digest:
                    raise ExternalAdoptionError("Idempotency key payload conflicts.")
                return duplicate
            adoption = await db.scalar(
                select(ExternalMilestoneAdoption)
                .where(
                    ExternalMilestoneAdoption.company_id == context.company.id,
                    ExternalMilestoneAdoption.id == adoption_id,
                )
                .with_for_update()
            )
            if adoption is None:
                raise LookupError("External adoption was not found.")
            if adoption.version != data.expected_adoption_version:
                raise ExternalAdoptionError("External adoption version is stale.")
            if data.starting_head != adoption.starting_head:
                raise ExternalAdoptionError("Starting HEAD does not match adoption.")
            if not FULL_SHA.fullmatch(data.current_head):
                raise ExternalAdoptionError("Current HEAD is invalid.")
            if data.occurred_at > now or (
                adoption.last_evidence_at is not None
                and data.occurred_at <= adoption.last_evidence_at
                and not data.correction
            ):
                raise ExternalAdoptionError("Evidence timestamp is stale.")
            if (
                data.progress_percent < adoption.progress_percent
                and not data.correction
            ):
                raise ExternalAdoptionError("Evidence progress regressed.")
            allowed_targets = ALLOWED_EVIDENCE_TRANSITIONS.get(adoption.status, set())
            if data.status not in allowed_targets:
                raise ExternalAdoptionError(
                    f"Evidence cannot move {adoption.status} to {data.status}."
                )
            target = data.status
            if target == "completed":
                if (
                    data.repository_state != "clean"
                    or data.blockers
                    or not data.commits
                    or not data.files_changed
                    or not data.validation_results
                    or not data.completion_evidence
                    or len(data.validation_results)
                    < len(adoption.validation_requirements)
                    or len(data.completion_evidence)
                    < len(adoption.expected_deliverables)
                ):
                    raise ExternalAdoptionError(
                        "Completion evidence is incomplete or unresolved."
                    )
                target = "waiting_review"
            evidence = ExternalMilestoneEvidence(
                company_id=context.company.id,
                adoption_id=adoption.id,
                expected_adoption_version=data.expected_adoption_version,
                status=data.status,
                progress_percent=data.progress_percent,
                current_activity=data.current_activity,
                starting_head=data.starting_head,
                current_head=data.current_head,
                commits=list(data.commits),
                files_changed=list(data.files_changed),
                validation_results=list(data.validation_results),
                dependencies=list(data.dependencies),
                blockers=list(data.blockers),
                completion_evidence=list(data.completion_evidence),
                owner_action_required=data.owner_action_required,
                repository_state=data.repository_state,
                correction=data.correction,
                idempotency_key=data.idempotency_key,
                evidence_digest=digest,
                submitted_by_user_id=context.user.id,
                occurred_at=data.occurred_at,
                received_at=now,
            )
            db.add(evidence)
            adoption.status = target
            adoption.progress_percent = data.progress_percent
            adoption.current_activity = data.current_activity
            adoption.current_head = data.current_head
            adoption.last_evidence_at = data.occurred_at
            adoption.version += 1
            adoption.updated_at = now
            milestone = await db.get(EngineeringMilestone, adoption.milestone_id)
            assert milestone is not None
            prior_status = milestone.status
            milestone.status = {
                "pending_start": milestone.status,
                "externally_running": "externally_running",
                "externally_validating": "externally_running",
                "externally_blocked": "blocked",
                "waiting_review": "waiting_review",
                "revision_requested": "externally_running",
            }[target]
            milestone.external_evidence = (
                f"{data.progress_percent}% · {data.current_activity or target}"
            )
            milestone.version += 1
            milestone.updated_at = now
            if milestone.status == "waiting_review":
                milestone.reviewed_at = now
            self._event(
                db,
                milestone,
                "external_evidence",
                prior_status,
                milestone.status,
                now,
            )
            await db.flush()
            return evidence

    async def owner_action(
        self,
        db: AsyncSession,
        *,
        context: AuthorizationContext,
        milestone_id: UUID,
        action: str,
        expected_version: int,
        reason: str | None,
    ) -> EngineeringMilestone | None:
        adoption = await self.adoption_for_milestone(
            db, company_id=context.company.id, milestone_id=milestone_id
        )
        if adoption is None:
            return None
        if action not in {"approve", "reject", "request_revision", "archive"}:
            return None
        await db.rollback()
        now = utc_now()
        async with db.begin():
            adoption = await db.scalar(
                select(ExternalMilestoneAdoption)
                .where(
                    ExternalMilestoneAdoption.company_id == context.company.id,
                    ExternalMilestoneAdoption.milestone_id == milestone_id,
                )
                .with_for_update()
            )
            milestone = await db.scalar(
                select(EngineeringMilestone)
                .where(
                    EngineeringMilestone.company_id == context.company.id,
                    EngineeringMilestone.id == milestone_id,
                )
                .with_for_update()
            )
            assert adoption is not None and milestone is not None
            prior_status = milestone.status
            if milestone.version != expected_version:
                raise ExternalAdoptionError("Milestone version is stale.")
            if action == "approve":
                if adoption.status != "waiting_review":
                    raise ExternalAdoptionError(
                        "External work is not ready for review."
                    )
                evidence = await db.scalar(
                    select(ExternalMilestoneEvidence)
                    .where(
                        ExternalMilestoneEvidence.adoption_id == adoption.id,
                        ExternalMilestoneEvidence.status == "completed",
                    )
                    .order_by(ExternalMilestoneEvidence.occurred_at.desc())
                )
                if evidence is None:
                    raise ExternalAdoptionError("Completion evidence is unavailable.")
                adoption.status = "completed"
                adoption.approval_by_user_id = context.user.id
                adoption.approval_at = now
                adoption.approval_evidence_digest = evidence.evidence_digest
                adoption.final_head = evidence.current_head
                milestone.status = "completed"
                milestone.completed_at = now
                milestone.reviewed_at = now
            elif action == "request_revision":
                if adoption.status != "waiting_review":
                    raise ExternalAdoptionError("External work is not in review.")
                adoption.status = "revision_requested"
                milestone.status = "externally_running"
            elif action == "reject":
                if adoption.status != "waiting_review":
                    raise ExternalAdoptionError("External work is not in review.")
                adoption.status = "externally_blocked"
                milestone.status = "blocked"
            else:
                if adoption.status not in {"completed", "cancelled"}:
                    raise ExternalAdoptionError("External work cannot be archived.")
                adoption.status = "archived"
                milestone.status = "archived"
            adoption.version += 1
            adoption.updated_at = now
            milestone.version += 1
            milestone.updated_at = now
            self._event(
                db,
                milestone,
                f"external_{action}",
                prior_status,
                milestone.status,
                now,
            )
            if action == "approve":
                await roadmap_service._promote(
                    db,
                    context.company.id,
                    milestone.roadmap_id,
                    now,
                    context.user.id,
                )
            await db.flush()
            return milestone

    @staticmethod
    def _event(
        db: AsyncSession,
        milestone: EngineeringMilestone,
        event_type: str,
        prior_status: str,
        new_status: str,
        now: datetime,
    ) -> None:
        db.add(
            EngineeringMilestoneEvent(
                company_id=milestone.company_id,
                roadmap_id=milestone.roadmap_id,
                milestone_id=milestone.id,
                event_type=event_type,
                prior_status=prior_status,
                new_status=new_status,
                actor_user_id=None,
                reason="Authenticated external workstream evidence",
                occurred_at=now,
            )
        )


external_adoption_service = ExternalAdoptionService()
