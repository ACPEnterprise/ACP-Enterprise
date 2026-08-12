from collections.abc import AsyncIterator
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.engineering_control.commands import (
    ApproveEngineeringCommand,
    CreateEngineeringCommand,
)
from app.engineering_control.service import EngineeringControlService
from app.engineering_execution.adapters import (
    EngineeringAdapterReadiness,
    EngineeringExecutionAdapter,
    EngineeringExecutionAdapterRegistry,
)
from app.engineering_execution.contracts import (
    EngineeringExecutionRequest,
    EngineeringExecutionResult,
    EngineeringExecutionState,
    EngineeringExecutionStatus,
    EngineeringFailureClassification,
)
from app.engineering_execution.errors import (
    EngineeringExecutionCommandNotFoundError,
    EngineeringExecutionIneligibleError,
    EngineeringExecutionPermissionError,
)
from app.engineering_execution.models import EngineeringExecution
from app.engineering_execution.service import EngineeringExecutionService
from app.events.models import BusinessEvent
from app.platform.audit.models import AuditRecord
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import (
    EngineeringCommandPermission,
    EngineeringExecutionPermission,
)
from tests.engineering_control.test_engineering_command_service import (
    ServiceFixture,
    context_with_permissions,
    seed_service_fixture,
    utc_now,
)


class FakeAdapter(EngineeringExecutionAdapter):
    def __init__(self, identifier: str = "test-provider") -> None:
        self._identifier = identifier
        self.readiness_calls = 0
        self.execution_calls = 0

    @property
    def provider_identifier(self) -> str:
        return self._identifier

    async def validate_readiness(self) -> EngineeringAdapterReadiness:
        self.readiness_calls += 1
        return EngineeringAdapterReadiness(False, "foundation_only")

    async def execute(
        self, request: EngineeringExecutionRequest
    ) -> EngineeringExecutionResult:
        self.execution_calls += 1
        raise AssertionError("DF.5B foundation must not execute")


@pytest_asyncio.fixture
async def execution_database() -> AsyncIterator[ServiceFixture]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    fixture = await seed_service_fixture(factory)
    try:
        yield fixture
    finally:
        await engine.dispose()


def execution_context(
    source: AuthorizationContext,
    *,
    permitted: bool = True,
    active: bool = True,
) -> AuthorizationContext:
    membership = replace(source.membership, status="active" if active else "revoked")
    permissions = (EngineeringExecutionPermission.REQUEST,) if permitted else ()
    return AuthorizationContext(
        user=source.user,
        company=source.company,
        membership=membership,
        authorized_branches=source.authorized_branches,
        active_branch=source.active_branch,
        effective_roles=(),
        effective_permissions=context_with_permissions(
            source.user, source.company, membership, permissions
        ).effective_permissions,
        credential_version=source.credential_version,
        authorization_version=source.authorization_version,
    )


async def approved_command(
    fixture: ServiceFixture,
    *,
    expires_in_hours: int = 2,
    instruction: str = "Inspect only the approved execution bridge boundary.",
    requested_code_changes: bool = True,
    expected_branch: str = "customer-management-v1",
    expected_head: str = "a" * 40,
):
    now = utc_now()
    command_context = context_with_permissions(
        fixture.context.user,
        fixture.context.company,
        fixture.context.membership,
        tuple(EngineeringCommandPermission.ALL),
    )
    control = EngineeringControlService()
    async with fixture.factory() as session:
        command = await control.create_command(
            session,
            context=command_context,
            command=CreateEngineeringCommand(
                command_type="owner_instruction",
                owner_instruction=instruction,
                repository_key="acp-enterprise",
                expected_branch=expected_branch,
                expected_head=expected_head,
                requested_code_changes=requested_code_changes,
                expires_at=now + timedelta(hours=expires_in_hours),
                idempotency_key=uuid4().hex,
                execution_boundary={
                    "allowed_repository": "acp-enterprise",
                    "allowed_branch": expected_branch,
                    "expected_head": expected_head,
                    "allowed_paths": ["backend/app/**"],
                    "forbidden_paths": [".git/**", ".env*", "**/.env*"],
                    "permitted_operations": [
                        "inspect",
                        "validate",
                        *(
                            [
                                "modify",
                                "commit",
                                "mechanical_reconcile",
                                "push",
                            ]
                            if requested_code_changes
                            else []
                        ),
                    ],
                    "validation_requirements": ["git diff --check"],
                },
            ),
            now=now,
        )
    async with fixture.factory() as session:
        return await control.approve_command(
            session,
            context=command_context,
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
            now=now + timedelta(minutes=1),
        )


def test_contracts_and_adapter_registry_are_immutable_and_provider_neutral() -> None:
    request = EngineeringExecutionRequest(
        command_id=uuid4(),
        ecid="ECID-2026-000001",
        repository_key="acp-enterprise",
        expected_repository_baseline="a" * 40,
        expected_branch="customer-management-v1",
        expected_head="a" * 40,
        authorized_code_changes=True,
        instruction="Inspect the boundary.",
        instruction_digest="b" * 64,
        request_digest="c" * 64,
        correlation_id=uuid4(),
    )
    with pytest.raises(FrozenInstanceError):
        request.expected_head = "d" * 40  # type: ignore[misc]
    adapter = FakeAdapter()
    registry = EngineeringExecutionAdapterRegistry((adapter,))
    assert registry.resolve("test-provider") is adapter
    assert registry.resolve("unknown") is None
    with pytest.raises(ValueError):
        EngineeringExecutionAdapterRegistry((adapter, FakeAdapter()))


@pytest.mark.asyncio
async def test_approved_command_persists_disconnected_execution_and_evidence(
    execution_database: ServiceFixture,
) -> None:
    fixture = execution_database
    command = await approved_command(fixture)
    adapter = FakeAdapter()
    service = EngineeringExecutionService(
        adapters=EngineeringExecutionAdapterRegistry((adapter,)),
        provider_identifier=adapter.provider_identifier,
    )
    context = execution_context(fixture.context)
    requested_at = utc_now()
    async with fixture.factory() as session:
        result = await service.request_execution(
            session,
            context=context,
            command_id=command.id,
            now=requested_at,
        )
    assert result.state is EngineeringExecutionState.EXECUTION_NOT_CONNECTED
    assert result.status is EngineeringExecutionStatus.DISCONNECTED
    assert (
        result.failure_classification
        is EngineeringFailureClassification.PROVIDER_NOT_CONNECTED
    )
    assert result.started_at is result.finished_at is None
    assert result.output_references == ()
    assert result.evidence_summary["execution_connected"] is False
    assert result.validation_summary["validation_started"] is False
    assert adapter.readiness_calls == 1
    assert adapter.execution_calls == 0

    async with fixture.factory() as session:
        stored = await service.get_execution(
            session, context=context, execution_id=result.execution_id
        )
        audit_count = await session.scalar(
            select(func.count(AuditRecord.id)).where(
                AuditRecord.resource_id == result.execution_id
            )
        )
        event_count = await session.scalar(
            select(func.count(BusinessEvent.id)).where(
                BusinessEvent.entity_id == result.execution_id
            )
        )
    assert stored.version == 1
    assert stored.company_id == fixture.context.company.id
    assert stored.command_id == command.id
    assert stored.ecid == command.ecid
    assert stored.instruction_digest == command.instruction_digest
    assert audit_count == event_count == 1
    with pytest.raises(TypeError):
        stored.evidence_summary["changed"] = True  # type: ignore[index]


@pytest.mark.asyncio
async def test_request_is_idempotent_and_company_scoped(
    execution_database: ServiceFixture,
) -> None:
    fixture = execution_database
    command = await approved_command(fixture)
    service = EngineeringExecutionService()
    context = execution_context(fixture.context)
    async with fixture.factory() as session:
        first = await service.request_execution(
            session, context=context, command_id=command.id
        )
    async with fixture.factory() as session:
        second = await service.request_execution(
            session, context=context, command_id=command.id
        )
    assert second == first
    assert second.provider_identifier == "unassigned"

    other = execution_context(fixture.other_context)
    async with fixture.factory() as session:
        with pytest.raises(EngineeringExecutionCommandNotFoundError):
            await service.request_execution(
                session, context=other, command_id=command.id
            )
        with pytest.raises(EngineeringExecutionCommandNotFoundError):
            await service.get_execution(
                session, context=other, execution_id=first.execution_id
            )


@pytest.mark.asyncio
async def test_permission_membership_and_command_eligibility_fail_closed(
    execution_database: ServiceFixture,
) -> None:
    fixture = execution_database
    command = await approved_command(fixture)
    service = EngineeringExecutionService()
    for context in (
        execution_context(fixture.context, permitted=False),
        execution_context(fixture.context, active=False),
    ):
        async with fixture.factory() as session:
            with pytest.raises(EngineeringExecutionPermissionError):
                await service.request_execution(
                    session, context=context, command_id=command.id
                )
    command_context = context_with_permissions(
        fixture.context.user,
        fixture.context.company,
        fixture.context.membership,
        tuple(EngineeringCommandPermission.ALL),
    )
    now = utc_now()
    async with fixture.factory() as session:
        awaiting = await EngineeringControlService().create_command(
            session,
            context=command_context,
            command=CreateEngineeringCommand(
                command_type="owner_instruction",
                owner_instruction="Inspect only.",
                repository_key="acp-enterprise",
                expected_branch="customer-management-v1",
                expected_head="b" * 40,
                requested_code_changes=False,
                expires_at=now + timedelta(hours=1),
                idempotency_key=uuid4().hex,
                execution_boundary={
                    "allowed_repository": "acp-enterprise",
                    "allowed_branch": "customer-management-v1",
                    "expected_head": "b" * 40,
                    "allowed_paths": ["**"],
                    "forbidden_paths": [".git/**", ".env*", "**/.env*"],
                    "permitted_operations": ["inspect", "validate"],
                    "validation_requirements": ["git diff --check"],
                },
            ),
            now=now,
        )
    async with fixture.factory() as session:
        with pytest.raises(EngineeringExecutionIneligibleError):
            await service.request_execution(
                session,
                context=execution_context(fixture.context),
                command_id=awaiting.id,
                now=now,
            )


@pytest.mark.asyncio
async def test_database_constraints_version_and_deterministic_listing(
    execution_database: ServiceFixture,
) -> None:
    fixture = execution_database
    commands = [await approved_command(fixture) for _ in range(2)]
    service = EngineeringExecutionService()
    context = execution_context(fixture.context)
    results = []
    for command in commands:
        async with fixture.factory() as session:
            results.append(
                await service.request_execution(
                    session, context=context, command_id=command.id
                )
            )
    async with fixture.factory() as session:
        listed = await service.repository.list_for_company(
            session, company_id=fixture.context.company.id
        )
    assert {item.id for item in listed} == {result.execution_id for result in results}
    assert list(listed) == sorted(
        listed, key=lambda item: (item.created_at, item.id), reverse=True
    )

    async with fixture.factory() as session:
        entity = await session.scalar(
            select(EngineeringExecution).where(
                EngineeringExecution.id == results[0].execution_id
            )
        )
        assert entity is not None
        entity.version = 0
        with pytest.raises(IntegrityError):
            await session.commit()
