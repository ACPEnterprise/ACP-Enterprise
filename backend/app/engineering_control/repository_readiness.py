from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering_capacity.models import EngineeringWorkerCapacity
from app.engineering_control.mobile.roadmaps import (
    EngineeringMilestone,
    EngineeringRoadmap,
)
from app.engineering_control.scheduler.models import (
    EngineeringCapacityBinding,
    EngineeringPermanentCapacity,
)
from app.engineering_execution.models import EngineeringExecution
from app.worker_control.models import EngineeringWorker

READINESS_TTL = timedelta(minutes=2)
ACTIVE_EXECUTION_STATES = frozenset({"queued", "starting", "running"})


def repository_preparation_required(
    *, requested_code_changes: bool, evidence: dict[str, object]
) -> bool:
    """Return whether Start requires assigned-provider repository readiness."""

    return requested_code_changes or "proof_role" in evidence


def active_readiness_target_eligible(
    *,
    milestone_status: str,
    milestone_reconciliation_state: str,
    command_id: UUID | None,
    execution_id: UUID | None,
    execution_state: str | None,
    execution_finished_at: datetime | None,
    execution_evidence: dict[str, object] | None,
) -> bool:
    """Return whether a milestone still needs repository preparation.

    A command with an existing execution is immutable historical lineage unless
    that execution is the milestone's currently running authority.  In
    particular, changing a milestone projection back to ``ready`` must not make
    a completed or reconciliation-required execution an active worker target.
    """

    if (
        milestone_status not in {"ready", "running"}
        or milestone_reconciliation_state != "current"
    ):
        return False
    if command_id is None or execution_id is None:
        return True
    evidence = execution_evidence or {}
    return (
        milestone_status == "running"
        and execution_state in ACTIVE_EXECUTION_STATES
        and execution_finished_at is None
        and evidence.get("reconciliation_required") is not True
    )


def readiness_semantics(readiness: object) -> dict[str, object] | None:
    """Return only evidence that can change the meaning of an owner action.

    ``prepared_at`` is observation metadata. Worker heartbeat persistence is the
    authoritative operational-freshness signal, so refreshing it must not rotate
    the milestone's optimistic-concurrency token.
    """
    if not isinstance(readiness, dict):
        return None
    keys = (
        "repository_key",
        "branch",
        "candidate_head",
        "observed_head",
        "provider_software_sha",
        "worker_id",
        "ready",
        "reason_code",
    )
    return {key: readiness.get(key) for key in keys}


def readiness_requires_milestone_update(
    existing: object,
    incoming: object,
    *,
    current_readiness_state: str | None,
    desired_readiness_state: str,
) -> bool:
    return (
        readiness_semantics(existing) != readiness_semantics(incoming)
        or current_readiness_state != desired_readiness_state
    )


@dataclass(frozen=True)
class RepositoryReadinessTarget:
    milestone_id: UUID
    repository_key: str
    branch: str
    candidate_head: str


def readiness_is_current(
    evidence: dict[str, object],
    *,
    repository_key: str,
    branch: str,
    candidate_head: str,
    worker_id: UUID | None = None,
    now: datetime | None = None,
) -> bool:
    readiness = evidence.get("provider_repository_readiness")
    if not isinstance(readiness, dict):
        return False
    observed_at = now or datetime.now(timezone.utc)
    try:
        prepared_at = datetime.fromisoformat(str(readiness["prepared_at"]))
    except (KeyError, TypeError, ValueError):
        return False
    return (
        prepared_at.tzinfo is not None
        and prepared_at <= observed_at
        and observed_at - prepared_at <= READINESS_TTL
        and readiness.get("ready") is True
        and readiness.get("repository_key") == repository_key
        and readiness.get("branch") == branch
        and readiness.get("candidate_head") == candidate_head
        and readiness.get("observed_head") == candidate_head
        and readiness.get("provider_software_sha") == candidate_head
        and (worker_id is None or readiness.get("worker_id") == str(worker_id))
    )


def readiness_prepared_at(readiness: object) -> datetime | None:
    if not isinstance(readiness, dict):
        return None
    try:
        prepared_at = datetime.fromisoformat(str(readiness["prepared_at"]))
    except (KeyError, TypeError, ValueError):
        return None
    return prepared_at if prepared_at.tzinfo is not None else None


class RepositoryReadinessService:
    async def start_admission_is_current(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        milestone_id: UUID,
        repository_key: str,
        branch: str,
        authoritative_head: str,
        requested_code_changes: bool,
        evidence: dict[str, object],
        now: datetime,
    ) -> bool:
        """Evaluate the canonical repository gate shared by Roadmap and Start."""

        if not repository_preparation_required(
            requested_code_changes=requested_code_changes,
            evidence=evidence,
        ):
            return True
        if evidence.get("authoritative_head") != authoritative_head:
            return False
        return await self.is_current_for_milestone(
            session,
            company_id=company_id,
            milestone_id=milestone_id,
            repository_key=repository_key,
            branch=branch,
            candidate_head=authoritative_head,
            evidence=evidence,
            now=now,
        )

    async def is_current_for_milestone(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        milestone_id: UUID,
        repository_key: str,
        branch: str,
        candidate_head: str,
        evidence: dict[str, object],
        now: datetime,
    ) -> bool:
        worker_id = await session.scalar(
            select(EngineeringWorkerCapacity.worker_id)
            .join(
                EngineeringCapacityBinding,
                EngineeringCapacityBinding.worker_capacity_id
                == EngineeringWorkerCapacity.id,
            )
            .join(
                EngineeringPermanentCapacity,
                EngineeringPermanentCapacity.id
                == EngineeringCapacityBinding.permanent_capacity_id,
            )
            .join(
                EngineeringMilestone,
                EngineeringMilestone.permanent_capacity_identity
                == EngineeringPermanentCapacity.identity_code,
            )
            .join(
                EngineeringWorker,
                EngineeringWorker.id == EngineeringWorkerCapacity.worker_id,
            )
            .where(
                EngineeringMilestone.company_id == company_id,
                EngineeringMilestone.id == milestone_id,
                EngineeringCapacityBinding.company_id == company_id,
                EngineeringCapacityBinding.state == "active",
                EngineeringWorkerCapacity.company_id == company_id,
                EngineeringWorkerCapacity.operational_state == "available",
                EngineeringWorkerCapacity.health_state == "healthy",
                EngineeringWorker.company_id == company_id,
                EngineeringWorker.lifecycle_state == "available",
                EngineeringWorker.last_heartbeat_at >= now - READINESS_TTL,
            )
        )
        return worker_id is not None and readiness_is_current(
            evidence,
            repository_key=repository_key,
            branch=branch,
            candidate_head=candidate_head,
            worker_id=worker_id,
            now=now,
        )

    async def targets(
        self, session: AsyncSession, *, company_id: UUID, worker_id: UUID
    ) -> tuple[RepositoryReadinessTarget, ...]:
        rows = (
            await session.execute(
                select(
                    EngineeringMilestone,
                    EngineeringRoadmap,
                    EngineeringExecution,
                )
                .join(
                    EngineeringRoadmap,
                    EngineeringRoadmap.id == EngineeringMilestone.roadmap_id,
                )
                .outerjoin(
                    EngineeringExecution,
                    and_(
                        EngineeringExecution.company_id
                        == EngineeringMilestone.company_id,
                        EngineeringExecution.command_id
                        == EngineeringMilestone.command_id,
                    ),
                )
                .join(
                    EngineeringPermanentCapacity,
                    EngineeringPermanentCapacity.identity_code
                    == EngineeringMilestone.permanent_capacity_identity,
                )
                .join(
                    EngineeringCapacityBinding,
                    EngineeringCapacityBinding.permanent_capacity_id
                    == EngineeringPermanentCapacity.id,
                )
                .join(
                    EngineeringWorkerCapacity,
                    EngineeringWorkerCapacity.id
                    == EngineeringCapacityBinding.worker_capacity_id,
                )
                .where(
                    EngineeringMilestone.company_id == company_id,
                    EngineeringMilestone.status.in_(("ready", "running")),
                    EngineeringMilestone.reconciliation_state == "current",
                    EngineeringPermanentCapacity.company_id == company_id,
                    EngineeringCapacityBinding.company_id == company_id,
                    EngineeringCapacityBinding.state == "active",
                    EngineeringWorkerCapacity.company_id == company_id,
                    EngineeringWorkerCapacity.worker_id == worker_id,
                )
            )
        ).all()
        return tuple(
            RepositoryReadinessTarget(
                milestone_id=milestone.id,
                repository_key=roadmap.repository_key,
                branch=roadmap.expected_branch,
                candidate_head=roadmap.expected_head,
            )
            for milestone, roadmap, execution in rows
            if active_readiness_target_eligible(
                milestone_status=milestone.status,
                milestone_reconciliation_state=milestone.reconciliation_state,
                command_id=milestone.command_id,
                execution_id=execution.id if execution is not None else None,
                execution_state=execution.state if execution is not None else None,
                execution_finished_at=(
                    execution.finished_at if execution is not None else None
                ),
                execution_evidence=(
                    execution.evidence_summary if execution is not None else None
                ),
            )
        )

    async def record(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        worker_id: UUID,
        milestone_id: UUID,
        repository_key: str,
        branch: str,
        candidate_head: str,
        observed_head: str,
        provider_software_sha: str,
        prepared_at: datetime,
        ready: bool,
        reason_code: str | None,
    ) -> None:
        if prepared_at.tzinfo is None:
            raise ValueError("Repository readiness timestamp must include a timezone.")
        targets = {
            item.milestone_id: item
            for item in await self.targets(
                session, company_id=company_id, worker_id=worker_id
            )
        }
        target = targets.get(milestone_id)
        if target is None or (
            target.repository_key,
            target.branch,
            target.candidate_head,
        ) != (repository_key, branch, candidate_head):
            raise ValueError(
                "Repository readiness does not match an assigned milestone."
            )
        milestone = await session.scalar(
            select(EngineeringMilestone)
            .where(
                EngineeringMilestone.company_id == company_id,
                EngineeringMilestone.id == milestone_id,
            )
            .with_for_update()
        )
        if milestone is None:
            raise ValueError("Repository readiness milestone was not found.")
        evidence = dict(milestone.starting_commit_evidence)
        incoming = {
            "repository_key": repository_key,
            "branch": branch,
            "candidate_head": candidate_head,
            "observed_head": observed_head,
            "provider_software_sha": provider_software_sha,
            "worker_id": str(worker_id),
            "prepared_at": prepared_at.isoformat(),
            "ready": ready and observed_head == candidate_head,
            "reason_code": reason_code,
        }
        existing = evidence.get("provider_repository_readiness")
        existing_prepared_at = readiness_prepared_at(existing)
        if existing_prepared_at is not None:
            if prepared_at < existing_prepared_at:
                raise ValueError(
                    "Repository readiness observation is older than durable evidence."
                )
            if prepared_at == existing_prepared_at and readiness_semantics(
                existing
            ) != readiness_semantics(incoming):
                raise ValueError(
                    "Repository readiness observation conflicts at the same timestamp."
                )
        desired_readiness_state = (
            "ready"
            if ready and observed_head == candidate_head
            else "preparing_environment"
        )
        if not readiness_requires_milestone_update(
            existing,
            incoming,
            current_readiness_state=milestone.readiness_state,
            desired_readiness_state=desired_readiness_state,
        ):
            # Persist authenticated freshness without rotating the owner's
            # optimistic-concurrency token for semantically identical truth.
            if existing_prepared_at is None or prepared_at > existing_prepared_at:
                evidence["provider_repository_readiness"] = incoming
                milestone.starting_commit_evidence = evidence
            return
        evidence["provider_repository_readiness"] = incoming
        milestone.starting_commit_evidence = evidence
        milestone.readiness_state = desired_readiness_state
        milestone.updated_at = datetime.now(timezone.utc)
        milestone.version += 1


repository_readiness_service = RepositoryReadinessService()
