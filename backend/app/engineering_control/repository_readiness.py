from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
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
from app.worker_control.models import EngineeringWorker

READINESS_TTL = timedelta(minutes=2)


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
    try:
        prepared_at = datetime.fromisoformat(str(readiness["prepared_at"]))
    except (KeyError, TypeError, ValueError):
        return False
    current = now or datetime.now(timezone.utc)
    return (
        readiness.get("ready") is True
        and readiness.get("repository_key") == repository_key
        and readiness.get("branch") == branch
        and readiness.get("candidate_head") == candidate_head
        and readiness.get("observed_head") == candidate_head
        and (worker_id is None or readiness.get("worker_id") == str(worker_id))
        and current - READINESS_TTL <= prepared_at <= current + timedelta(seconds=30)
    )


class RepositoryReadinessService:
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
                select(EngineeringMilestone, EngineeringRoadmap)
                .join(
                    EngineeringRoadmap,
                    EngineeringRoadmap.id == EngineeringMilestone.roadmap_id,
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
                    EngineeringMilestone.status == "ready",
                    EngineeringMilestone.reconciliation_state == "current",
                    EngineeringMilestone.requested_code_changes.is_(True),
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
            for milestone, roadmap in rows
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
        evidence["provider_repository_readiness"] = {
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
        milestone.starting_commit_evidence = evidence
        milestone.readiness_state = (
            "ready"
            if ready and observed_head == candidate_head
            else "preparing_environment"
        )
        milestone.updated_at = datetime.now(timezone.utc)
        milestone.version += 1


repository_readiness_service = RepositoryReadinessService()
