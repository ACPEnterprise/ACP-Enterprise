import hashlib
import json
import subprocess
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.engineering_control.mobile.control import EngineeringWorkstreamControl
from app.engineering_control.mobile.roadmaps import (
    EngineeringMilestone,
    EngineeringMilestoneEvent,
    EngineeringRoadmap,
    RoadmapService,
)
from app.engineering_control.mobile.service import MobileEngineeringControlService
from app.engineering_control.models import EngineeringCommand
from app.engineering_control.repository_operation.git_adapter import (
    ProductionBoundedGitAdapter,
)
from app.engineering_control.review.models import EngineeringExecutionReview
from app.engineering_control.scheduler.manifest import release_bound_manifest
from app.engineering_control.scheduler.models import (
    EngineeringSchedulerEvent,
    EngineeringSchedulerSnapshot,
)
from app.engineering_control.workstream_runtime import (
    EngineeringWorkstreamEvent,
    EngineeringWorkstreamRuntime,
)
from app.engineering_execution.controlled.contracts import ControlledCommandType
from app.engineering_execution.controlled.models import ControlledExecutionOfferModel
from app.engineering_execution.controlled.repository import (
    ControlledExecutionRepository,
)
from app.engineering_execution.controlled.service import (
    ControlledExecutionService,
    calculate_adoption_evidence_digest,
)
from app.engineering_execution.models import EngineeringExecution
from app.engineering_execution.service import EngineeringExecutionService
from app.execution_nodes.models import EngineeringExecutionNode
from app.execution_nodes.workspaces import WorkspaceManager
from app.platform.audit.models import AuditRecord
from app.worker_control.models import WorkerLease
from tests.engineering_control.test_engineering_command_service import (
    ServiceFixture,
    seed_service_fixture,
    utc_now,
)
from tests.engineering_execution.test_engineering_execution import (
    approved_command,
    execution_context,
)
from tests.worker_control.transport.persistence.test_transport_persistence import (
    established_transport,
)

PATH = "frontend/src/api/technician.ts"
FINGERPRINT = "0" * 64


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ("git", *args), cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def published_repository(root: Path) -> tuple[str, str, str]:
    working, remote = root / "working", root / "remote.git"
    working.mkdir()
    remote.mkdir()
    git(working, "init", "-b", "customer-management-v1")
    git(working, "config", "user.name", "ACP Test")
    git(working, "config", "user.email", "acp-test@example.invalid")
    target = working / PATH
    target.parent.mkdir(parents=True)
    target.write_text("baseline\n", encoding="utf-8")
    git(working, "add", PATH)
    git(working, "commit", "-m", "baseline")
    starting_head = git(working, "rev-parse", "HEAD")
    target.write_text("published\n", encoding="utf-8")
    git(working, "add", PATH)
    git(working, "commit", "-m", "published result")
    commit = git(working, "rev-parse", "HEAD")
    git(remote, "init", "--bare")
    git(working, "remote", "add", "origin", str(remote))
    git(working, "push", "origin", "customer-management-v1")
    target.write_text("published\ncurrent repair\n", encoding="utf-8")
    git(working, "add", PATH)
    git(working, "commit", "-m", "later authorized repair")
    current_head = git(working, "rev-parse", "HEAD")
    git(working, "push", "origin", "customer-management-v1")
    return starting_head, commit, current_head


@pytest_asyncio.fixture
async def adoption_database() -> AsyncIterator[ServiceFixture]:
    engine = create_async_engine(settings.database_url)
    fixture = await seed_service_fixture(
        async_sessionmaker(engine, expire_on_commit=False)
    )
    try:
        yield fixture
    finally:
        await engine.dispose()


@pytest.mark.parametrize("legacy_boundary", [False, True])
@pytest.mark.asyncio
async def test_expired_published_result_adoption_preserves_history_and_opens_review(
    adoption_database: ServiceFixture, tmp_path: Path, legacy_boundary: bool
) -> None:
    fixture = adoption_database
    starting_head, commit, current_head = published_repository(tmp_path)
    _, worker_session = await established_transport(fixture)
    command = await approved_command(fixture, requested_code_changes=True)
    boundary = {
        "boundary_id": "TEST.1",
        "boundary_version": 2,
        "fingerprint": FINGERPRINT,
        "allowed_paths": ["frontend/src/api/technician*.ts"],
        "forbidden_paths": ["backend/**", ".env*"],
        "permitted_operations": ["inspect", "modify", "validate", "commit", "push"],
        "validation_requirements": ["git diff --check"],
    }
    manifest = release_bound_manifest(starting_head)
    tech = next(item for item in manifest.milestones if item.milestone_code == "TECH.1")
    assert tech.execution_boundary is not None
    boundary_version = 2
    boundary_fingerprint = FINGERPRINT
    if legacy_boundary:
        boundary_version = tech.execution_boundary.boundary_version
        boundary_fingerprint = tech.execution_boundary.fingerprint
        boundary = {
            "allowed_repository": command.repository_key,
            "allowed_branch": command.expected_branch,
            "expected_head": starting_head,
            "allowed_paths": list(tech.execution_boundary.allowed_paths),
            "forbidden_paths": list(tech.execution_boundary.forbidden_paths),
            "permitted_operations": list(tech.execution_boundary.permitted_operations),
            "validation_requirements": list(
                tech.execution_boundary.validation_requirements
            ),
        }
    boundary_digest = hashlib.sha256(
        json.dumps(boundary, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    now = utc_now()
    async with fixture.factory() as database, database.begin():
        durable_command = await database.get(EngineeringCommand, command.id)
        assert durable_command is not None
        durable_command.expected_head = starting_head
        durable_command.execution_boundary = boundary
        durable_command.execution_boundary_digest = boundary_digest
        roadmap = EngineeringRoadmap(
            company_id=fixture.context.company.id,
            title="Adoption regression",
            repository_key=command.repository_key,
            expected_branch=command.expected_branch,
            expected_head=starting_head,
            status="active",
            created_at=now,
            updated_at=now,
        )
        database.add(roadmap)
        await database.flush()
        milestone = EngineeringMilestone(
            company_id=fixture.context.company.id,
            roadmap_id=roadmap.id,
            position=1,
            title="Adopt result",
            milestone_code="TECH.1" if legacy_boundary else "TEST.1",
            reconciliation_state="current",
            objective="Regression",
            owning_workstream="Field Service" if legacy_boundary else "Engineering",
            owning_branch=command.expected_branch,
            status="running",
            definition_approved=True,
            requested_code_changes=True,
            command_id=command.id,
            created_at=now,
            updated_at=now,
        )
        database.add(milestone)
        await database.flush()
        if legacy_boundary:
            historical_at = durable_command.created_at - timedelta(seconds=1)
            database.add(
                EngineeringSchedulerSnapshot(
                    company_id=fixture.context.company.id,
                    scheduler_version=manifest.scheduler_version,
                    fingerprint=manifest.fingerprint,
                    manifest=manifest.model_dump(mode="json"),
                    source_documents=list(manifest.source_documents),
                    active=False,
                    created_at=historical_at,
                    activated_at=historical_at,
                )
            )
            database.add(
                EngineeringSchedulerEvent(
                    company_id=fixture.context.company.id,
                    event_type="scheduler.milestone_reconciled",
                    scheduler_version=manifest.scheduler_version,
                    milestone_code="TECH.1",
                    permanent_capacity_identity="OM1",
                    record_id=milestone.id,
                    details={"non_destructive": True},
                    idempotency_key=f"legacy-boundary:{command.id}",
                    occurred_at=historical_at,
                )
            )
    async with fixture.factory() as database:
        execution = await EngineeringExecutionService().request_execution(
            database,
            context=execution_context(fixture.context),
            command_id=command.id,
        )
    async with fixture.factory() as database, database.begin():
        durable_execution = await database.get(
            EngineeringExecution, execution.execution_id
        )
        assert durable_execution is not None
        node = EngineeringExecutionNode(
            company_id=fixture.context.company.id,
            worker_id=worker_session.context.worker_id,
            name="Adoption test node",
            provider_identifier=worker_session.context.provider_identifier,
            credential_fingerprint="f" * 64,
            capabilities=["engineering.execute"],
            status="active",
            enrolled_at=now,
            expires_at=now + timedelta(days=1),
            version=1,
        )
        database.add(node)
        await database.flush()
        offer = await ControlledExecutionRepository.create_offer(
            database,
            company_id=fixture.context.company.id,
            command_id=command.id,
            execution_id=execution.execution_id,
            correlation_id=durable_execution.correlation_id,
            workspace_id="adoption-test",
            command_type=ControlledCommandType.EXECUTE_CODE,
            payload={
                "node_id": str(node.id),
                "repository_key": command.repository_key,
                "expected_branch": command.expected_branch,
                "expected_head": starting_head,
            },
            expires_at=command.expires_at,
            lease_seconds=30,
            now=now,
        )
        acquired = await ControlledExecutionService().acquire_in_transaction(
            database,
            worker_context=worker_session.context,
            session_id=worker_session.session_id,
            offer_id=offer.id,
            now=now + timedelta(seconds=1),
        )
        await (
            ControlledExecutionService().reconcile_expired_worker_leases_in_transaction(
                database,
                worker_context=worker_session.context,
                now=now + timedelta(seconds=32),
            )
        )
    completed_at = now + timedelta(seconds=20)
    run = {
        "identity": "git diff --check",
        "argv": ["git", "diff", "--check", "HEAD"],
        "working_directory": ".",
        "started_at": (now + timedelta(seconds=10)).isoformat(),
        "completed_at": completed_at.isoformat(),
        "duration_ms": 10_000,
        "exit_code": 0,
        "passed": True,
        "failure_summary": None,
        "toolchain": {"git": "test"},
        "stdout": {"text": "", "truncated": False, "redacted": False},
        "stderr": {"text": "", "truncated": False, "redacted": False},
    }
    requirements = list(boundary["validation_requirements"])
    runs = [
        {**run, "identity": identity, "argv": ["tool", identity]}
        for identity in requirements
    ]
    output: dict[str, object] = {
        "workspace_id": "adoption-test",
        "repository_key": command.repository_key,
        "branch": command.expected_branch,
        "head": commit,
        "starting_head": starting_head,
        "commit_sha": commit,
        "published_commit_sha": commit,
        "remote_head_before": starting_head,
        "mechanically_reconciled": False,
        "clean": True,
        "file_count": 1,
        "file_boundary": [PATH],
        "repository_mutated": True,
        "validation": {identity: True for identity in requirements},
        "validation_runs": runs,
        "validation_environment": {"mode": "isolated"},
        "evidence": {
            "phases": [
                "composed",
                "workspace_ready",
                "executing",
                "validating",
                "commit_ready",
                "publishing_result",
                "completed",
            ]
        },
    }
    evidence_digest = calculate_adoption_evidence_digest(
        command_id=command.id,
        execution_id=execution.execution_id,
        ecid=command.ecid,
        offer_id=offer.id,
        lease_id=acquired.lease_id,
        starting_head=starting_head,
        commit_sha=commit,
        commit_parent=starting_head,
        remote_head=commit,
        boundary_version=boundary_version,
        boundary_fingerprint=boundary_fingerprint,
        boundary_digest=boundary_digest,
        provider_completed_at=completed_at,
        workspace_clean=True,
        output=output,
    )
    service = ControlledExecutionService(
        publication_adapter=ProductionBoundedGitAdapter(tmp_path / "working")
    )
    async with fixture.factory() as database:
        result, review_id, adopted_at = await service.adopt_expired_result(
            database,
            context=fixture.context,
            execution_id=execution.execution_id,
            command_id=command.id,
            ecid=command.ecid,
            offer_id=offer.id,
            lease_id=acquired.lease_id,
            starting_head=starting_head,
            commit_sha=commit,
            commit_parent=starting_head,
            remote_head=commit,
            boundary_version=boundary_version,
            boundary_fingerprint=boundary_fingerprint,
            boundary_digest=boundary_digest,
            provider_completed_at=completed_at,
            provider_evidence_digest=evidence_digest,
            workspace_clean=True,
            output=output,
            idempotency_key="adopt:test:one",
            now=now + timedelta(minutes=1),
        )
    async with fixture.factory() as database:
        (
            duplicate,
            duplicate_review_id,
            duplicate_adopted_at,
        ) = await service.adopt_expired_result(
            database,
            context=fixture.context,
            execution_id=execution.execution_id,
            command_id=command.id,
            ecid=command.ecid,
            offer_id=offer.id,
            lease_id=acquired.lease_id,
            starting_head=starting_head,
            commit_sha=commit,
            commit_parent=starting_head,
            remote_head=commit,
            boundary_version=boundary_version,
            boundary_fingerprint=boundary_fingerprint,
            boundary_digest=boundary_digest,
            provider_completed_at=completed_at,
            provider_evidence_digest=evidence_digest,
            workspace_clean=True,
            output=output,
            idempotency_key="adopt:test:one",
            now=now + timedelta(minutes=2),
        )
    assert duplicate.id == result.id
    assert duplicate_review_id == review_id
    assert duplicate_adopted_at == adopted_at
    assert result.repository_mutated is True
    assert result.output["commit_sha"] == commit
    assert result.output["adoption"]["historical_publication_head"] == commit
    assert (
        result.output["adoption"]["current_authoritative_head_at_adoption"]
        == current_head
    )
    expected_source = (
        "legacy_scheduler_snapshot" if legacy_boundary else "frozen_command"
    )
    assert result.output["adoption"]["boundary_evidence"]["source"] == expected_source
    assert adopted_at > completed_at
    assert git(tmp_path / "working", "rev-parse", "HEAD") == current_head
    assert (
        git(
            tmp_path / "working",
            "ls-remote",
            "origin",
            "refs/heads/customer-management-v1",
        ).split()[0]
        == current_head
    )
    readiness = WorkspaceManager(
        tmp_path / "provider-workspaces",
        {"acp-enterprise": tmp_path / "working"},
    ).prepare_repository("acp-enterprise", "customer-management-v1", current_head)
    assert readiness.ready is True
    assert readiness.observed_head == current_head
    async with fixture.factory() as database, database.begin():
        durable_milestone = await database.get(EngineeringMilestone, milestone.id)
        assert durable_milestone is not None
        durable_milestone.status = "ready"
        durable_milestone.updated_at = adopted_at
        control = EngineeringWorkstreamControl(
            company_id=fixture.context.company.id,
            command_id=command.id,
            desired_state="active",
            requested_action="start",
            actor_user_id=fixture.context.user.id,
            version=1,
            created_at=now,
            updated_at=now,
        )
        database.add(control)
        await database.flush()
        database.add(
            EngineeringWorkstreamRuntime(
                company_id=fixture.context.company.id,
                command_id=command.id,
                control_id=control.id,
                worker_id=result.worker_id,
                worker_session_id=result.session_id,
                acknowledged_control_version=control.version,
                acknowledged_action="start",
                runtime_state="acknowledged",
                worker_health="healthy",
                progress_percent=100,
                current_activity="Published result ready for owner review",
                reason_code="reconciliation_required",
                acknowledged_at=now,
                acknowledgement_expires_at=adopted_at - timedelta(seconds=1),
                heartbeat_at=adopted_at,
                updated_at=adopted_at,
                version=2,
            )
        )
    async with fixture.factory() as database:
        await RoadmapService().reconcile(database, context=fixture.context)
    async with fixture.factory() as database:
        await RoadmapService().reconcile(database, context=fixture.context)
    async with fixture.factory() as database:
        converged_milestone = await database.get(EngineeringMilestone, milestone.id)
        converged_runtime = await database.scalar(
            select(EngineeringWorkstreamRuntime).where(
                EngineeringWorkstreamRuntime.command_id == command.id
            )
        )
        convergence_events = tuple(
            (
                await database.scalars(
                    select(EngineeringWorkstreamEvent).where(
                        EngineeringWorkstreamEvent.command_id == command.id,
                        EngineeringWorkstreamEvent.reason_code
                        == "adopted_result_owner_review",
                    )
                )
            ).all()
        )
        milestone_events = tuple(
            (
                await database.scalars(
                    select(EngineeringMilestoneEvent).where(
                        EngineeringMilestoneEvent.milestone_id == milestone.id,
                        EngineeringMilestoneEvent.event_type
                        == "adopted_result_reconciled",
                    )
                )
            ).all()
        )
        review_count = await database.scalar(
            select(func.count(EngineeringExecutionReview.id)).where(
                EngineeringExecutionReview.command_id == command.id
            )
        )
        execution_count = await database.scalar(
            select(func.count(EngineeringExecution.id)).where(
                EngineeringExecution.command_id == command.id
            )
        )
    assert converged_milestone is not None
    assert converged_milestone.status == "waiting_review"
    assert converged_runtime is not None
    assert converged_runtime.runtime_state == "waiting_for_owner"
    assert converged_runtime.reason_code == "adopted_result_owner_review"
    assert len(convergence_events) == 1
    assert len(milestone_events) == 1
    assert review_count == 1
    assert execution_count == 1
    heartbeat_at = adopted_at + timedelta(minutes=6)
    async with fixture.factory() as database, database.begin():
        drifted_runtime = await database.scalar(
            select(EngineeringWorkstreamRuntime).where(
                EngineeringWorkstreamRuntime.command_id == command.id
            )
        )
        assert drifted_runtime is not None
        drifted_runtime.runtime_state = "recovering"
        drifted_runtime.worker_health = "unhealthy"
        drifted_runtime.reason_code = "heartbeat_expired"
        drifted_runtime.version += 1
        drifted_runtime.updated_at = heartbeat_at
        database.add(
            EngineeringWorkstreamEvent(
                company_id=fixture.context.company.id,
                command_id=command.id,
                control_id=drifted_runtime.control_id,
                control_version=drifted_runtime.acknowledged_control_version,
                worker_id=drifted_runtime.worker_id,
                worker_session_id=drifted_runtime.worker_session_id,
                event_type="runtime_transition",
                action=drifted_runtime.acknowledged_action,
                runtime_state="recovering",
                reason_code="heartbeat_expired",
                idempotency_key=f"heartbeat-expired:{drifted_runtime.id}:fixture",
                occurred_at=heartbeat_at,
            )
        )
    async with fixture.factory() as database:
        await RoadmapService().reconcile(database, context=fixture.context)
    async with fixture.factory() as database:
        await RoadmapService().reconcile(database, context=fixture.context)
        roadmaps = await RoadmapService().list(database, context=fixture.context)
        milestones = await RoadmapService().milestones(
            database, context=fixture.context
        )
        assert roadmaps[0].id == milestone.roadmap_id
        assert any(item.id == milestone.id for item in milestones)
    async with fixture.factory() as database:
        restored_runtime = await database.scalar(
            select(EngineeringWorkstreamRuntime).where(
                EngineeringWorkstreamRuntime.command_id == command.id
            )
        )
        convergence_count = await database.scalar(
            select(func.count(EngineeringWorkstreamEvent.id)).where(
                EngineeringWorkstreamEvent.command_id == command.id,
                EngineeringWorkstreamEvent.reason_code == "adopted_result_owner_review",
            )
        )
        heartbeat_count = await database.scalar(
            select(func.count(EngineeringWorkstreamEvent.id)).where(
                EngineeringWorkstreamEvent.command_id == command.id,
                EngineeringWorkstreamEvent.reason_code == "heartbeat_expired",
            )
        )
        assert restored_runtime is not None
        assert restored_runtime.runtime_state == "waiting_for_owner"
        assert restored_runtime.worker_health == "unhealthy"
        assert restored_runtime.reason_code == "heartbeat_expired"
        assert convergence_count == 1
        assert heartbeat_count == 1
    async with fixture.factory() as database:
        stored_offer = await database.get(ControlledExecutionOfferModel, offer.id)
        stored_lease = await database.get(WorkerLease, acquired.lease_id)
        review = await database.get(EngineeringExecutionReview, review_id)
        stored_command = await database.get(EngineeringCommand, command.id)
        audits = (
            await database.scalars(
                select(AuditRecord).where(
                    AuditRecord.action == "engineering.controlled_result_adopted",
                    AuditRecord.resource_id == execution.execution_id,
                )
            )
        ).all()
    async with fixture.factory() as database:
        projection = await MobileEngineeringControlService().workstream_detail(
            database,
            context=fixture.context,
            command_id=command.id,
            now=adopted_at,
        )
    assert stored_offer is not None and stored_offer.state == "expired"
    assert stored_lease is not None and stored_lease.status == "expired"
    assert review is not None and review.state == "pending"
    assert len(audits) == 1
    assert stored_command is not None
    assert stored_command.execution_boundary == boundary
    assert audits[0].details["boundary_evidence"]["source"] == expected_source
    assert projection.pipeline_status == "waiting_for_owner"
    assert projection.authoritative_state == "waiting_for_owner_review"
    assert projection.owner_action_required is True
    assert projection.next_owner_action == "review_execution_result"
    assert "start" not in projection.available_actions
    assert projection.result_commit_sha == commit
    assert projection.result_publication_status == "published"
    assert projection.result_adoption_status == "adopted"
    assert projection.execution_status == "completed"
    assert projection.validation_status == "completed"
    assert projection.preview_deployment_status == "not_performed"
    assert projection.owner_review_digest == review.review_digest
    assert projection.owner_review_version == review.version
    assert projection.owner_review_action_available is True
    assert projection.failure_classification is None
    assert projection.historical_recovery_context[0]["classification"] == (
        "historical_transport_recovery"
    )
