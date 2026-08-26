import asyncio
import subprocess
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.database.session import get_database_session
from app.engineering_control.repository_authorization.contracts import (
    RepositoryAuthorizationState,
)
from app.engineering_control.repository_authorization.models import (
    EngineeringRepositoryAuthorization,
)
from app.engineering_control.repository_authorization.service import (
    EngineeringRepositoryAuthorizationService,
)
from app.engineering_control.repository_operation.contracts import (
    RepositoryOperationState,
)
from app.engineering_control.repository_operation.errors import (
    RepositoryOperationGitError,
    RepositoryOperationNotFoundError,
    RepositoryOperationValidationError,
)
from app.engineering_control.repository_operation.git_adapter import (
    ProductionBoundedGitAdapter,
)
from app.engineering_control.repository_operation.models import (
    EngineeringRepositoryOperation,
    EngineeringRepositoryOperationEvent,
)
from app.engineering_control.repository_operation.records import (
    ExecuteRepositoryCommit,
)
from app.engineering_control.repository_operation.router import (
    get_repository_operation_service,
    router,
)
from app.engineering_control.repository_operation.service import (
    EngineeringRepositoryOperationService,
    utc_now,
)
from app.engineering_execution.status.service import MobileExecutionStatusService
from app.events.models import BusinessEvent
from app.platform.permissions.codes import (
    EngineeringCommandPermission,
    EngineeringRepositoryOperationPermission,
)
from app.platform.permissions.dependencies import get_authorization_context
from tests.engineering_control.repository_authorization.test_repository_authorization import (
    BOUNDARY,
    accepted_review,
    request_for,
)
from tests.engineering_control.test_engineering_command_service import (
    ServiceFixture,
    context_with_permissions,
    seed_service_fixture,
)


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ("git", *arguments),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def repository(root: Path) -> str:
    git(root, "init", "-b", "customer-management-v1")
    git(root, "config", "user.name", "ACP Test")
    git(root, "config", "user.email", "acp-test@example.invalid")
    for path in BOUNDARY:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("baseline\n", encoding="utf-8")
    git(root, "add", "--", *BOUNDARY)
    git(root, "commit", "-m", "baseline")
    base = git(root, "rev-parse", "HEAD")
    for path in BOUNDARY:
        (root / path).write_text("reviewed change\n", encoding="utf-8")
    return base


def test_bounded_adapter_verifies_exact_remote_publication(tmp_path: Path) -> None:
    working = tmp_path / "working"
    remote = tmp_path / "remote.git"
    working.mkdir()
    remote.mkdir()
    base = repository(working)
    git(remote, "init", "--bare")
    git(working, "remote", "add", "origin", str(remote))
    git(working, "add", "--", *BOUNDARY)
    git(working, "commit", "-m", "published result")
    commit = git(working, "rev-parse", "HEAD")
    git(working, "push", "origin", "customer-management-v1")

    adapter = ProductionBoundedGitAdapter(working)
    proof = adapter.inspect_commit(commit)
    assert proof.parent == base
    assert proof.files == BOUNDARY
    assert adapter.inspect_remote_head("customer-management-v1") == commit
    assert (
        adapter.verify_historical_publication("customer-management-v1", commit)
        == commit
    )


def test_historical_publication_accepts_descendant_tip_without_moving_branch(
    tmp_path: Path,
) -> None:
    working = tmp_path / "working"
    remote = tmp_path / "remote.git"
    working.mkdir()
    remote.mkdir()
    repository(working)
    git(remote, "init", "--bare")
    git(working, "remote", "add", "origin", str(remote))
    git(working, "add", "--", *BOUNDARY)
    git(working, "commit", "-m", "published result")
    result_commit = git(working, "rev-parse", "HEAD")
    git(working, "push", "origin", "customer-management-v1")
    (working / BOUNDARY[0]).write_text("later repair\n", encoding="utf-8")
    git(working, "add", BOUNDARY[0])
    git(working, "commit", "-m", "later authorized repair")
    current_head = git(working, "rev-parse", "HEAD")
    git(working, "push", "origin", "customer-management-v1")

    adapter = ProductionBoundedGitAdapter(working)
    assert (
        adapter.verify_historical_publication(
            "customer-management-v1", result_commit
        )
        == current_head
    )
    assert git(working, "rev-parse", "HEAD") == current_head


def test_historical_publication_rejects_diverged_or_unrelated_object(
    tmp_path: Path,
) -> None:
    working = tmp_path / "working"
    remote = tmp_path / "remote.git"
    working.mkdir()
    remote.mkdir()
    base = repository(working)
    git(remote, "init", "--bare")
    git(working, "remote", "add", "origin", str(remote))
    git(working, "add", "--", *BOUNDARY)
    git(working, "commit", "-m", "result on replaced lineage")
    result_commit = git(working, "rev-parse", "HEAD")
    git(working, "push", "origin", "customer-management-v1")
    git(remote, "update-ref", "refs/heads/customer-management-v1", base)

    adapter = ProductionBoundedGitAdapter(working)
    with pytest.raises(RepositoryOperationGitError) as error:
        adapter.verify_historical_publication(
            "customer-management-v1", result_commit
        )
    assert error.value.classification == "publication_not_in_authoritative_lineage"


@pytest_asyncio.fixture
async def operation_database() -> AsyncIterator[ServiceFixture]:
    engine = create_async_engine(settings.database_url)
    fixture = await seed_service_fixture(
        async_sessionmaker(engine, expire_on_commit=False)
    )
    try:
        yield fixture
    finally:
        await engine.dispose()


def owner_context(fixture: ServiceFixture):
    permissions = (
        *EngineeringCommandPermission.ALL,
        *EngineeringRepositoryOperationPermission.ALL,
    )
    return context_with_permissions(
        fixture.context.user,
        fixture.context.company,
        fixture.context.membership,
        permissions,
    )


async def authorization(
    fixture: ServiceFixture,
    *,
    base: str,
    suffix: str,
):
    _, review, _ = await accepted_review(fixture, expected_head=base)
    context = owner_context(fixture)
    async with fixture.factory() as session:
        record = await EngineeringRepositoryAuthorizationService().request(
            session,
            context=context,
            command=request_for(review, suffix=suffix),
        )
    return record, context


def execute_command(record, *, suffix: str = "one") -> ExecuteRepositoryCommit:
    return ExecuteRepositoryCommit(
        authorization_id=record.id,
        capability_id=record.capability_id,
        authorization_digest=record.authorization_digest,
        commit_subject="feat(devx): create bounded test commit",
        idempotency_key=f"repository-operation-{suffix}",
    )


@pytest.mark.asyncio
async def test_exact_commit_consumes_authorization_once(
    operation_database: ServiceFixture,
    tmp_path: Path,
) -> None:
    base = repository(tmp_path)
    authorization_record, context = await authorization(
        operation_database, base=base, suffix="success"
    )
    service = EngineeringRepositoryOperationService(
        adapter=ProductionBoundedGitAdapter(tmp_path)
    )
    command = execute_command(authorization_record)
    async with operation_database.factory() as session:
        result = await service.execute(session, context=context, command=command)
    assert result.state is RepositoryOperationState.SUCCEEDED
    assert result.resulting_commit_sha == git(tmp_path, "rev-parse", "HEAD")
    assert git(tmp_path, "status", "--porcelain") == ""
    assert git(tmp_path, "show", "-s", "--format=%s", "HEAD") == command.commit_subject
    assert (
        tuple(
            sorted(
                git(
                    tmp_path, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"
                ).splitlines()
            )
        )
        == BOUNDARY
    )

    async with operation_database.factory() as session:
        stored_authorization = await session.get(
            EngineeringRepositoryAuthorization, authorization_record.id
        )
        events = (
            await session.scalars(
                select(BusinessEvent).where(BusinessEvent.entity_id == result.id)
            )
        ).all()
    assert stored_authorization is not None
    assert stored_authorization.state == RepositoryAuthorizationState.CONSUMED.value
    assert {event.event_type for event in events} == {
        "engineering_control.repository_operation_requested",
        "engineering_control.repository_operation_reserved",
        "engineering_control.repository_operation_started",
        "engineering_control.repository_operation_succeeded",
    }
    assert all("file_boundary" not in event.payload for event in events)
    assert all("authorization_digest" not in event.payload for event in events)
    async with operation_database.factory() as session:
        status = await MobileExecutionStatusService().get(
            session,
            context=context,
            command_id=result.command_id,
        )
    assert status.repository_operation_status == "succeeded"
    assert (
        status.repository_operation_resulting_commit_sha == result.resulting_commit_sha
    )
    assert status.repository_operation_owner_attention_required is False
    assert not hasattr(status, "capability_id")
    assert not hasattr(status, "authorization_digest")

    async with operation_database.factory() as session:
        replay = await service.execute(session, context=context, command=command)
    assert replay.id == result.id
    assert git(tmp_path, "rev-list", "--count", "HEAD") == "2"
    with pytest.raises(RepositoryOperationValidationError):
        async with operation_database.factory() as session:
            await service.execute(
                session,
                context=context,
                command=replace(
                    command,
                    idempotency_key="repository-operation-second-use",
                ),
            )


@pytest.mark.asyncio
async def test_preflight_failures_preserve_authorization(
    operation_database: ServiceFixture,
    tmp_path: Path,
) -> None:
    base = repository(tmp_path)
    authorization_record, context = await authorization(
        operation_database, base=base, suffix="extra"
    )
    (tmp_path / "unapproved.txt").write_text("unexpected\n", encoding="utf-8")
    service = EngineeringRepositoryOperationService(
        adapter=ProductionBoundedGitAdapter(tmp_path)
    )
    with pytest.raises(RepositoryOperationGitError):
        async with operation_database.factory() as session:
            await service.execute(
                session,
                context=context,
                command=execute_command(authorization_record, suffix="extra"),
            )
    async with operation_database.factory() as session:
        operation = await session.scalar(
            select(EngineeringRepositoryOperation).where(
                EngineeringRepositoryOperation.authorization_id
                == authorization_record.id
            )
        )
        stored_authorization = await session.get(
            EngineeringRepositoryAuthorization, authorization_record.id
        )
    assert operation is not None
    assert operation.state == RepositoryOperationState.FAILED.value
    assert stored_authorization is not None
    assert stored_authorization.state == RepositoryAuthorizationState.AUTHORIZED.value
    assert git(tmp_path, "rev-parse", "HEAD") == base


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutation", "classification"),
    (
        ("wrong_branch", "branch_mismatch"),
        ("staged_file", "index_not_empty"),
        ("missing_file", "authorized_file_missing"),
    ),
)
async def test_repository_state_mismatch_fails_closed(
    operation_database: ServiceFixture,
    tmp_path: Path,
    mutation: str,
    classification: str,
) -> None:
    base = repository(tmp_path)
    authorization_record, context = await authorization(
        operation_database, base=base, suffix=mutation
    )
    if mutation == "wrong_branch":
        git(tmp_path, "checkout", "-b", "unexpected-branch")
    elif mutation == "staged_file":
        git(tmp_path, "add", "--", BOUNDARY[0])
    else:
        (tmp_path / BOUNDARY[0]).unlink()
    service = EngineeringRepositoryOperationService(
        adapter=ProductionBoundedGitAdapter(tmp_path)
    )
    with pytest.raises(RepositoryOperationGitError) as error:
        async with operation_database.factory() as session:
            await service.execute(
                session,
                context=context,
                command=execute_command(authorization_record, suffix=mutation),
            )
    assert error.value.classification == classification
    assert git(tmp_path, "rev-parse", base) == base


@pytest.mark.asyncio
async def test_invalid_commit_subject_is_rejected_before_reservation(
    operation_database: ServiceFixture,
    tmp_path: Path,
) -> None:
    base = repository(tmp_path)
    authorization_record, context = await authorization(
        operation_database, base=base, suffix="subject"
    )
    service = EngineeringRepositoryOperationService(
        adapter=ProductionBoundedGitAdapter(tmp_path)
    )
    with pytest.raises(RepositoryOperationValidationError):
        async with operation_database.factory() as session:
            await service.execute(
                session,
                context=context,
                command=replace(
                    execute_command(authorization_record, suffix="subject"),
                    commit_subject="invalid\nsubject",
                ),
            )
    async with operation_database.factory() as session:
        assert (
            await session.scalar(
                select(EngineeringRepositoryOperation.id).where(
                    EngineeringRepositoryOperation.authorization_id
                    == authorization_record.id
                )
            )
            is None
        )


@pytest.mark.asyncio
async def test_concurrent_reservation_has_one_winner(
    operation_database: ServiceFixture,
    tmp_path: Path,
) -> None:
    base = repository(tmp_path)
    authorization_record, context = await authorization(
        operation_database, base=base, suffix="concurrent"
    )
    service = EngineeringRepositoryOperationService(
        adapter=ProductionBoundedGitAdapter(tmp_path)
    )
    first = execute_command(authorization_record, suffix="concurrent-a")
    second = replace(first, idempotency_key="repository-operation-concurrent-b")

    async def run(command):
        async with operation_database.factory() as session:
            return await service._reserve(
                session,
                context=context,
                command=command,
                subject=command.commit_subject,
                now=authorization_record.authorized_at,
            )

    results = await asyncio.gather(run(first), run(second), return_exceptions=True)
    assert sum(not isinstance(item, BaseException) for item in results) == 1
    async with operation_database.factory() as session:
        operations = (
            await session.scalars(
                select(EngineeringRepositoryOperation).where(
                    EngineeringRepositoryOperation.authorization_id
                    == authorization_record.id
                )
            )
        ).all()
    assert len(operations) == 1


@pytest.mark.asyncio
async def test_reconciliation_detects_existing_commit_without_recommitting(
    operation_database: ServiceFixture,
    tmp_path: Path,
) -> None:
    base = repository(tmp_path)
    authorization_record, context = await authorization(
        operation_database, base=base, suffix="reconcile"
    )
    adapter = ProductionBoundedGitAdapter(tmp_path)
    service = EngineeringRepositoryOperationService(adapter=adapter)
    command = execute_command(authorization_record, suffix="reconcile")
    now = utc_now()
    async with operation_database.factory() as session:
        reserved = await service._reserve(
            session,
            context=context,
            command=command,
            subject=command.commit_subject,
            now=now,
        )
    service._validate_preflight(adapter, reserved)
    async with operation_database.factory() as session:
        executing = await service._start(
            session, context=context, operation=reserved, now=now
        )
    adapter.stage_exact_files(executing.file_boundary)
    service._validate_staged(adapter, executing)
    sha = adapter.create_commit(executing.commit_subject)
    service._validate_post_commit(adapter, executing, sha)
    async with operation_database.factory() as session:
        await service._finalize_failure(
            session,
            context=context,
            operation=executing,
            error=RepositoryOperationGitError(
                "persistence_finalization_uncertain",
                "Commit exists but persistence is uncertain.",
            ),
            reconciliation=True,
            resulting_commit_sha=sha,
            now=utc_now(),
        )
    async with operation_database.factory() as session:
        reconciled = await service.reconcile(
            session,
            context=context,
            command=command,
            operation_id=executing.id,
        )
    assert reconciled.state is RepositoryOperationState.SUCCEEDED
    assert reconciled.resulting_commit_sha == sha
    assert git(tmp_path, "rev-list", "--count", "HEAD") == "2"


def test_adapter_rejects_secret_and_arbitrary_surface(tmp_path: Path) -> None:
    repository(tmp_path)
    adapter = ProductionBoundedGitAdapter(tmp_path)
    (tmp_path / BOUNDARY[0]).write_text(
        "OPENAI_API_KEY=not-a-real-secret\n", encoding="utf-8"
    )
    (tmp_path / BOUNDARY[1]).write_text("safe\n", encoding="utf-8")
    adapter.stage_exact_files(BOUNDARY)
    with pytest.raises(RepositoryOperationGitError) as error:
        adapter.validate_staged_content()
    assert error.value.classification == "secret_pattern_detected"
    assert not hasattr(adapter, "run")
    assert not hasattr(adapter, "execute")


@pytest.mark.asyncio
async def test_cross_company_is_concealed(
    operation_database: ServiceFixture,
    tmp_path: Path,
) -> None:
    base = repository(tmp_path)
    authorization_record, _ = await authorization(
        operation_database, base=base, suffix="tenant"
    )
    service = EngineeringRepositoryOperationService(
        adapter=ProductionBoundedGitAdapter(tmp_path)
    )
    other_context = context_with_permissions(
        operation_database.other_context.user,
        operation_database.other_context.company,
        operation_database.other_context.membership,
        (EngineeringRepositoryOperationPermission.READ,),
    )
    with pytest.raises(RepositoryOperationNotFoundError):
        async with operation_database.factory() as session:
            await service.get(
                session,
                context=other_context,
                operation_id=uuid4(),
            )
    async with operation_database.factory() as session:
        assert (
            await session.scalar(
                select(EngineeringRepositoryOperationEvent.id).where(
                    EngineeringRepositoryOperationEvent.company_id
                    == operation_database.other_context.company.id,
                    EngineeringRepositoryOperationEvent.operation_id
                    == authorization_record.id,
                )
            )
            is None
        )


@pytest.mark.asyncio
async def test_http_api_is_bounded_and_permission_checked(
    operation_database: ServiceFixture,
    tmp_path: Path,
) -> None:
    base = repository(tmp_path)
    authorization_record, context = await authorization(
        operation_database, base=base, suffix="http"
    )
    service = EngineeringRepositoryOperationService(
        adapter=ProductionBoundedGitAdapter(tmp_path)
    )
    command = execute_command(authorization_record, suffix="http")
    app = FastAPI()
    app.include_router(router)
    active_context = {"value": context}

    async def session_override() -> AsyncIterator[AsyncSession]:
        async with operation_database.factory() as session:
            yield session

    async def context_override():
        return active_context["value"]

    app.dependency_overrides[get_database_session] = session_override
    app.dependency_overrides[get_authorization_context] = context_override
    app.dependency_overrides[get_repository_operation_service] = lambda: service
    payload = {
        "authorization_id": str(command.authorization_id),
        "capability_id": str(command.capability_id),
        "authorization_digest": command.authorization_digest,
        "commit_subject": command.commit_subject,
        "idempotency_key": command.idempotency_key,
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        readiness = await client.post(
            "/api/v1/engineering/repository-operations/readiness",
            json=payload,
        )
        assert readiness.status_code == 200
        assert readiness.json()["eligible"] is True
        executed = await client.post(
            "/api/v1/engineering/repository-operations/execute",
            json=payload,
        )
        assert executed.status_code == 200
        body = executed.json()
        assert body["state"] == "succeeded"
        assert "capability_id" not in body
        assert "authorization_digest" not in body
        listed = await client.get("/api/v1/engineering/repository-operations")
        assert listed.status_code == 200
        assert listed.json()["items"][0]["id"] == body["id"]

        active_context["value"] = context_with_permissions(
            context.user,
            context.company,
            context.membership,
            (EngineeringRepositoryOperationPermission.READ,),
        )
        forbidden = await client.post(
            "/api/v1/engineering/repository-operations/execute",
            json={**payload, "idempotency_key": "repository-operation-forbidden"},
        )
        assert forbidden.status_code == 403
