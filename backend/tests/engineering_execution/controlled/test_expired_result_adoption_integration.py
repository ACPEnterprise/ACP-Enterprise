import hashlib
import json
import subprocess
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from app.core.config import settings
from app.engineering_control.mobile.roadmaps import (
    EngineeringMilestone,
    EngineeringRoadmap,
)
from app.engineering_control.mobile.service import MobileEngineeringControlService
from app.engineering_control.models import EngineeringCommand
from app.engineering_control.repository_operation.git_adapter import (
    ProductionBoundedGitAdapter,
)
from app.engineering_control.review.models import EngineeringExecutionReview
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
from app.platform.audit.models import AuditRecord
from app.worker_control.models import WorkerLease
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

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


def published_repository(root: Path) -> tuple[str, str]:
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
    return starting_head, commit


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


@pytest.mark.asyncio
async def test_expired_published_result_adoption_preserves_history_and_opens_review(
    adoption_database: ServiceFixture, tmp_path: Path
) -> None:
    fixture = adoption_database
    starting_head, commit = published_repository(tmp_path)
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
        database.add(
            EngineeringMilestone(
                company_id=fixture.context.company.id,
                roadmap_id=roadmap.id,
                position=1,
                title="Adopt result",
                milestone_code="TEST.1",
                reconciliation_state="current",
                objective="Regression",
                owning_workstream="Engineering",
                owning_branch=command.expected_branch,
                status="running",
                definition_approved=True,
                requested_code_changes=True,
                command_id=command.id,
                created_at=now,
                updated_at=now,
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
        "validation": {"git diff --check": True},
        "validation_runs": [run],
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
        boundary_version=2,
        boundary_fingerprint=FINGERPRINT,
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
            boundary_version=2,
            boundary_fingerprint=FINGERPRINT,
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
            boundary_version=2,
            boundary_fingerprint=FINGERPRINT,
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
    assert adopted_at > completed_at
    async with fixture.factory() as database:
        stored_offer = await database.get(ControlledExecutionOfferModel, offer.id)
        stored_lease = await database.get(WorkerLease, acquired.lease_id)
        review = await database.get(EngineeringExecutionReview, review_id)
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
    assert projection.pipeline_status == "waiting_for_owner"
    assert projection.authoritative_state == "waiting_for_owner_review"
    assert projection.owner_action_required is True
    assert projection.next_owner_action == "review_execution_result"
    assert "start" not in projection.available_actions
