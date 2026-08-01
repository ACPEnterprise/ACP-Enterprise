import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from app.core.config import settings
from app.engineering_control.mobile.external_adoption import (
    ExternalAdoptionError,
    ExternalAdoptionService,
    ExternalMilestoneEvidence,
)
from app.engineering_control.mobile.roadmaps import (
    EngineeringMilestone,
    EngineeringRoadmap,
    roadmap_service,
)
from app.engineering_control.mobile.schemas import ExternalEvidenceCreate
from app.engineering_control.models import EngineeringCommand
from app.engineering_control.workstream_runtime import EngineeringWorkstreamRuntime
from app.platform.permissions.codes import (
    EngineeringCommandPermission,
    EngineeringExecutionPermission,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.engineering_control.test_engineering_command_service import (
    ServiceFixture,
    context_with_permissions,
    seed_service_fixture,
)


@pytest_asyncio.fixture
async def database_factory():
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def seed_adoptable(factory) -> tuple[ServiceFixture, EngineeringMilestone]:
    fixture = await seed_service_fixture(factory)
    now = datetime.now(timezone.utc)
    async with factory() as session, session.begin():
        roadmap = EngineeringRoadmap(
            company_id=fixture.context.company.id,
            title="External roadmap",
            repository_key="acp-enterprise",
            expected_branch="customer-management-v1",
            expected_head="a" * 40,
            status="active",
            created_at=now,
            updated_at=now,
        )
        session.add(roadmap)
        await session.flush()
        milestone = EngineeringMilestone(
            company_id=fixture.context.company.id,
            roadmap_id=roadmap.id,
            position=1,
            title="Existing external work",
            objective="Adopt existing work without dispatching it.",
            owning_workstream="External",
            owning_branch="external-workstream",
            authority=[],
            constraints=[],
            dependencies=[],
            validation=["focused tests"],
            deliverables=["validated result"],
            stop_conditions=[],
            expected_completion_evidence=["commit and validation"],
            status="planned",
            definition_approved=True,
            requested_code_changes=True,
            externally_adoptable=True,
            created_at=now,
            updated_at=now,
        )
        session.add(milestone)
        await session.flush()
        successor = EngineeringMilestone(
            company_id=fixture.context.company.id,
            roadmap_id=roadmap.id,
            position=2,
            title="Successor milestone",
            objective="Continue only after owner approval and explicit Start.",
            owning_workstream="External",
            owning_branch="customer-management-v1",
            authority=[],
            constraints=[],
            dependencies=["Existing external work"],
            validation=["focused tests"],
            deliverables=["successor result"],
            stop_conditions=[],
            expected_completion_evidence=["validated result"],
            status="planned",
            definition_approved=True,
            requested_code_changes=True,
            externally_adoptable=False,
            created_at=now,
            updated_at=now,
        )
        session.add(successor)
        session.expunge(milestone)
    return fixture, milestone


def adoption_payload() -> dict[str, object]:
    return {
        "repository_key": "acp-enterprise",
        "branch": "external-workstream",
        "starting_head": "b" * 40,
        "starting_repository_clean": True,
        "worktree_identity": "/bounded/external-worktree",
        "owning_external_workstream": "External terminal",
        "declared_scope": ["existing milestone scope"],
        "protected_boundaries": ["production"],
        "expected_deliverables": ["validated result"],
        "validation_requirements": ["focused tests"],
        "evidence_format": "mission-control-external-v1",
        "responsible_source": "approved-external-terminal",
    }


def evidence_payload(
    *,
    version: int,
    occurred_at: datetime,
    status: str = "completed",
    progress: int = 100,
    idempotency_key: str = "external-completion-001",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "expected_adoption_version": version,
        "status": status,
        "progress_percent": progress,
        "current_activity": "Validation complete"
        if status == "completed"
        else "External implementation underway",
        "starting_head": "b" * 40,
        "current_head": "c" * 40,
        "commits": ["c" * 40] if status == "completed" else [],
        "files_changed": ["bounded/file.py"] if status == "completed" else [],
        "validation_results": ["focused tests passed"] if status == "completed" else [],
        "dependencies": [],
        "blockers": [],
        "completion_evidence": ["clean committed result"]
        if status == "completed"
        else [],
        "owner_action_required": status == "completed",
        "repository_state": "clean",
        "occurred_at": occurred_at.isoformat(),
        "idempotency_key": idempotency_key,
        "correction": False,
    }
    validated = ExternalEvidenceCreate.model_validate(
        {**payload, "evidence_digest": "0" * 64}
    )
    canonical = validated.model_dump(mode="json", exclude={"evidence_digest"})
    payload["evidence_digest"] = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return payload


@pytest.mark.asyncio
async def test_external_adoption_completion_review_and_promotion(
    database_factory,
) -> None:
    fixture, milestone = await seed_adoptable(database_factory)
    service = ExternalAdoptionService()
    async with database_factory() as session:
        adoption = await service.adopt(
            session,
            context=fixture.context,
            milestone_id=milestone.id,
            payload=adoption_payload(),
        )
        assert adoption.status == "pending_start"
        assert adoption.progress_percent == 0

    async with database_factory() as session:
        command_count = await session.scalar(
            select(func.count(EngineeringCommand.id)).where(
                EngineeringCommand.company_id == fixture.context.company.id
            )
        )
        runtime_count = await session.scalar(
            select(func.count(EngineeringWorkstreamRuntime.id)).where(
                EngineeringWorkstreamRuntime.company_id == fixture.context.company.id
            )
        )
        assert command_count == 0
        assert runtime_count == 0

    started_handoff = evidence_payload(
        version=adoption.version,
        occurred_at=datetime.now(timezone.utc) - timedelta(seconds=2),
        status="externally_running",
        progress=25,
        idempotency_key="external-progress-001",
    )
    async with database_factory() as session:
        started_evidence = await service.handoff(
            session,
            context=fixture.context,
            adoption_id=adoption.id,
            payload=started_handoff,
        )
        duplicate = await service.handoff(
            session,
            context=fixture.context,
            adoption_id=adoption.id,
            payload=started_handoff,
        )
        assert duplicate.id == started_evidence.id

    handoff = evidence_payload(
        version=adoption.version + 1,
        occurred_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    async with database_factory() as session:
        await service.handoff(
            session,
            context=fixture.context,
            adoption_id=adoption.id,
            payload=handoff,
        )

    async with database_factory() as session:
        waiting = await session.get(EngineeringMilestone, milestone.id)
        assert waiting is not None and waiting.status == "waiting_review"
        completed = await service.owner_action(
            session,
            context=fixture.context,
            milestone_id=milestone.id,
            action="approve",
            expected_version=waiting.version,
            reason=None,
        )
        assert completed is not None and completed.status == "completed"

    async with database_factory() as session:
        persisted = await service.adoption_for_milestone(
            session,
            company_id=fixture.context.company.id,
            milestone_id=milestone.id,
        )
        evidence_count = await session.scalar(
            select(func.count(ExternalMilestoneEvidence.id)).where(
                ExternalMilestoneEvidence.adoption_id == adoption.id
            )
        )
        command_count = await session.scalar(
            select(func.count(EngineeringCommand.id)).where(
                EngineeringCommand.company_id == fixture.context.company.id
            )
        )
        assert persisted is not None and persisted.status == "completed"
        assert persisted.approval_evidence_digest == handoff["evidence_digest"]
        assert evidence_count == 2
        assert command_count == 0
        successor = await session.scalar(
            select(EngineeringMilestone).where(
                EngineeringMilestone.roadmap_id == milestone.roadmap_id,
                EngineeringMilestone.title == "Successor milestone",
            )
        )
        assert successor is not None and successor.status == "ready"
        successor_id = successor.id
        successor_version = successor.version

    async with database_factory() as session:
        dispatch_context = context_with_permissions(
            fixture.context.user,
            fixture.context.company,
            fixture.context.membership,
            tuple(
                EngineeringCommandPermission.ALL | EngineeringExecutionPermission.ALL
            ),
        )
        started = await roadmap_service.action(
            session,
            context=dispatch_context,
            milestone_id=successor_id,
            action="start",
            expected_version=successor_version,
            reason="explicit_owner_start",
        )
        assert started.command_id is not None
        assert started.status == "running"

    async with database_factory() as session:
        adopted = await session.get(EngineeringMilestone, milestone.id)
        command_count = await session.scalar(
            select(func.count(EngineeringCommand.id)).where(
                EngineeringCommand.company_id == fixture.context.company.id
            )
        )
        assert adopted is not None and adopted.command_id is None
        assert command_count == 1


@pytest.mark.asyncio
async def test_external_adoption_rejects_ineligible_conflicts_and_stale_evidence(
    database_factory,
) -> None:
    fixture, milestone = await seed_adoptable(database_factory)
    service = ExternalAdoptionService()
    async with database_factory() as session:
        adoption = await service.adopt(
            session,
            context=fixture.context,
            milestone_id=milestone.id,
            payload=adoption_payload(),
        )
    async with database_factory() as session:
        with pytest.raises(ExternalAdoptionError, match="active adoption"):
            await service.adopt(
                session,
                context=fixture.context,
                milestone_id=milestone.id,
                payload=adoption_payload(),
            )
    stale = evidence_payload(
        version=adoption.version + 1,
        occurred_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    async with database_factory() as session:
        with pytest.raises(ExternalAdoptionError, match="version is stale"):
            await service.handoff(
                session,
                context=fixture.context,
                adoption_id=adoption.id,
                payload=stale,
            )
