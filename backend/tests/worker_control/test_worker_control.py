from collections.abc import AsyncIterator
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.engineering_execution.service import EngineeringExecutionService
from app.events.models import BusinessEvent
from app.execution_providers.contracts import (
    ExecutionProvider,
    ProviderCapabilities,
    ProviderCapability,
    ProviderExecutionRequest,
    ProviderExecutionResult,
    ProviderExecutionStatus,
    ProviderHealth,
    ProviderIdentity,
    immutable_mapping,
)
from app.execution_providers.registry import ExecutionProviderRegistry
from app.platform.audit.models import AuditRecord
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import WorkerControlPermission
from app.worker_control.contracts import (
    AuthenticatedWorkerContext,
    WorkerCapability,
    WorkerExecutionResult,
    WorkerFailureClassification,
    WorkerHealth,
    WorkerLeaseStatus,
    WorkerLifecycleState,
    WorkerResultStatus,
)
from app.worker_control.errors import (
    WorkerAuthenticationError,
    WorkerConflictError,
    WorkerControlPermissionError,
    WorkerLeaseError,
    WorkerLifecycleError,
    WorkerNotFoundError,
    WorkerValidationError,
)
from app.worker_control.models import WorkerHeartbeat, WorkerLease, WorkerResult
from app.worker_control.service import RegisterWorkerCommand, WorkerControlService
from tests.engineering_control.test_engineering_command_service import (
    ServiceFixture,
    context_with_permissions,
    seed_service_fixture,
    utc_now,
)
from tests.engineering_execution.test_engineering_execution import (
    approved_command,
    execution_context,
)


@pytest_asyncio.fixture
async def worker_database() -> AsyncIterator[ServiceFixture]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    fixture = await seed_service_fixture(factory)
    try:
        yield fixture
    finally:
        await engine.dispose()


def operator_context(
    source: AuthorizationContext,
    *,
    permitted: bool = True,
    active: bool = True,
) -> AuthorizationContext:
    membership = replace(source.membership, status="active" if active else "revoked")
    permissions = (WorkerControlPermission.MANAGE,) if permitted else ()
    return context_with_permissions(
        source.user, source.company, membership, permissions
    )


async def register_available_worker(
    fixture: ServiceFixture,
    *,
    name: str = "worker-one",
    provider_identifier: str = "local-provider",
    capabilities: tuple[WorkerCapability, ...] = (
        WorkerCapability.ENGINEERING_EXECUTE,
    ),
):
    service = WorkerControlService()
    now = utc_now()
    async with fixture.factory() as session:
        worker = await service.register_worker(
            session,
            context=operator_context(fixture.context),
            command=RegisterWorkerCommand(
                provider_identifier=provider_identifier,
                name=name,
                worker_version="1.0.0",
                capabilities=capabilities,
            ),
            now=now,
        )
    worker_context = AuthenticatedWorkerContext(
        company_id=worker.company_id,
        worker_id=worker.id,
        provider_identifier=worker.provider_identifier,
        authentication_subject=f"worker:{worker.id}",
        authenticated_at=now,
    )
    async with fixture.factory() as session:
        worker, heartbeat = await service.record_heartbeat(
            session,
            worker_context=worker_context,
            health=WorkerHealth.HEALTHY,
            now=now + timedelta(seconds=1),
        )
    return service, worker, worker_context, heartbeat


class FakeExecutionProvider(ExecutionProvider):
    def __init__(
        self,
        *,
        identifier: str = "codex",
        capabilities: tuple[ProviderCapability, ...] = (
            ProviderCapability.ENGINEERING_EXECUTE,
        ),
        available: bool = True,
    ) -> None:
        self._identity = ProviderIdentity(identifier, "Test Provider", "1")
        self._capabilities = ProviderCapabilities(capabilities)
        self.available = available
        self.requests: list[ProviderExecutionRequest] = []

    @property
    def identity(self) -> ProviderIdentity:
        return self._identity

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    async def health(self) -> ProviderHealth:
        return ProviderHealth(self.available, utc_now(), "test")

    async def execute(
        self, request: ProviderExecutionRequest
    ) -> ProviderExecutionResult:
        self.requests.append(request)
        instant = utc_now()
        return ProviderExecutionResult(
            provider_request_id=request.provider_request_id,
            execution_id=request.execution_id,
            provider_execution_id="provider-result-1",
            provider_identifier=self.identity.identifier,
            status=ProviderExecutionStatus.SUCCEEDED,
            started_at=instant,
            finished_at=instant,
            evidence_summary=immutable_mapping({"repository_mutated": False}),
            validation_summary=immutable_mapping({"tests_run": False}),
            output_references=("evidence://provider-result-1",),
            failure_classification=None,
        )


async def disconnected_execution(fixture: ServiceFixture):
    command = await approved_command(fixture)
    service = EngineeringExecutionService()
    async with fixture.factory() as session:
        return await service.request_execution(
            session,
            context=execution_context(fixture.context),
            command_id=command.id,
        )


def test_worker_contracts_are_immutable_and_provider_neutral() -> None:
    context = AuthenticatedWorkerContext(
        company_id=uuid4(),
        worker_id=uuid4(),
        provider_identifier="provider",
        authentication_subject="subject",
        authenticated_at=utc_now(),
    )
    with pytest.raises(FrozenInstanceError):
        context.worker_id = uuid4()  # type: ignore[misc]
    assert tuple(capability.value for capability in WorkerCapability) == (
        "engineering.execute",
        "review.package",
        "validation.run",
    )


@pytest.mark.asyncio
async def test_registration_is_company_scoped_validated_and_audited(
    worker_database: ServiceFixture,
) -> None:
    fixture = worker_database
    service, worker, _, heartbeat = await register_available_worker(fixture)
    assert worker.lifecycle_state is WorkerLifecycleState.AVAILABLE
    assert worker.version == 2
    assert heartbeat.worker_version == 2
    assert heartbeat.health is WorkerHealth.HEALTHY
    assert worker.capabilities == (WorkerCapability.ENGINEERING_EXECUTE,)

    async with fixture.factory() as session:
        audit_count = await session.scalar(
            select(func.count(AuditRecord.id)).where(
                AuditRecord.resource_id == worker.id
            )
        )
        heartbeat_count = await session.scalar(
            select(func.count(WorkerHeartbeat.id)).where(
                WorkerHeartbeat.worker_id == worker.id
            )
        )
        other_company = await service.repository.get_worker(
            session,
            company_id=fixture.other_context.company.id,
            worker_id=worker.id,
        )
    assert audit_count == heartbeat_count == 1
    assert other_company is None

    async with fixture.factory() as session:
        with pytest.raises(WorkerConflictError):
            await service.register_worker(
                session,
                context=operator_context(fixture.context),
                command=RegisterWorkerCommand(
                    provider_identifier="local-provider",
                    name="worker-one",
                    worker_version="2.0.0",
                    capabilities=(WorkerCapability.VALIDATION_RUN,),
                ),
            )
    async with fixture.factory() as session:
        with pytest.raises(WorkerValidationError):
            await service.register_worker(
                session,
                context=operator_context(fixture.context),
                command=RegisterWorkerCommand(
                    provider_identifier="unsafe provider",
                    name="worker",
                    worker_version="1",
                    capabilities=(),
                ),
            )


@pytest.mark.asyncio
async def test_operator_authorization_is_permission_based(
    worker_database: ServiceFixture,
) -> None:
    fixture = worker_database
    service = WorkerControlService()
    command = RegisterWorkerCommand(
        provider_identifier="provider",
        name="worker",
        worker_version="1",
        capabilities=(WorkerCapability.ENGINEERING_EXECUTE,),
    )
    async with fixture.factory() as session:
        with pytest.raises(WorkerControlPermissionError):
            await service.register_worker(
                session,
                context=operator_context(fixture.context, permitted=False),
                command=command,
            )
    async with fixture.factory() as session:
        with pytest.raises(WorkerControlPermissionError):
            await service.register_worker(
                session,
                context=operator_context(fixture.context, active=False),
                command=command,
            )


@pytest.mark.asyncio
async def test_worker_lifecycle_validation_and_repository_ordering(
    worker_database: ServiceFixture,
) -> None:
    fixture = worker_database
    service, first, first_context, _ = await register_available_worker(
        fixture, name="worker-a"
    )
    _, second, _, _ = await register_available_worker(fixture, name="worker-b")
    async with fixture.factory() as session:
        validated = await service.validate_worker(session, worker_context=first_context)
    assert validated == first
    async with fixture.factory() as session:
        offline = await service.set_worker_lifecycle(
            session,
            context=operator_context(fixture.context),
            worker_id=first.id,
            lifecycle_state=WorkerLifecycleState.OFFLINE,
        )
    assert offline.lifecycle_state is WorkerLifecycleState.OFFLINE
    async with fixture.factory() as session:
        disabled = await service.set_worker_lifecycle(
            session,
            context=operator_context(fixture.context),
            worker_id=first.id,
            lifecycle_state=WorkerLifecycleState.DISABLED,
        )
    assert disabled.lifecycle_state is WorkerLifecycleState.DISABLED
    async with fixture.factory() as session:
        workers = await service.repository.list_workers(
            session, company_id=fixture.context.company.id
        )
    assert {worker.id for worker in workers} >= {first.id, second.id}
    assert workers == tuple(
        sorted(
            workers, key=lambda worker: (worker.registered_at, worker.id), reverse=True
        )
    )
    async with fixture.factory() as session:
        with pytest.raises(WorkerLifecycleError):
            await service.record_heartbeat(
                session,
                worker_context=first_context,
                health=WorkerHealth.HEALTHY,
            )


@pytest.mark.asyncio
async def test_offer_and_lease_lifecycle_never_changes_execution(
    worker_database: ServiceFixture,
) -> None:
    fixture = worker_database
    service, worker, worker_context, _ = await register_available_worker(fixture)
    execution = await disconnected_execution(fixture)
    now = utc_now()
    async with fixture.factory() as session:
        offer = await service.issue_offer(
            session,
            context=operator_context(fixture.context),
            execution_id=execution.execution_id,
            capability_required=WorkerCapability.ENGINEERING_EXECUTE,
            lease_seconds=120,
            now=now,
        )
    assert offer.metadata["work_dispatched"] is False
    with pytest.raises(TypeError):
        offer.metadata["work_dispatched"] = True  # type: ignore[index]

    async with fixture.factory() as session:
        lease = await service.acquire_lease(
            session,
            worker_context=worker_context,
            offer=offer,
            now=now + timedelta(seconds=1),
        )
    assert lease.status is WorkerLeaseStatus.ACTIVE
    async with fixture.factory() as session:
        renewed = await service.renew_lease(
            session,
            worker_context=worker_context,
            lease_id=lease.id,
            expected_version=lease.version,
            lease_seconds=180,
            now=now + timedelta(seconds=2),
        )
    assert renewed.version == 2
    async with fixture.factory() as session:
        released = await service.release_lease(
            session,
            worker_context=worker_context,
            lease_id=lease.id,
            expected_version=renewed.version,
            now=now + timedelta(seconds=3),
        )
        stored_execution = await EngineeringExecutionService().get_execution(
            session,
            context=execution_context(fixture.context),
            execution_id=execution.execution_id,
        )
    assert released.status is WorkerLeaseStatus.RELEASED
    assert stored_execution.state.value == "execution_not_connected"
    async with fixture.factory() as session:
        stored_worker = await service.repository.get_worker(
            session, company_id=worker.company_id, worker_id=worker.id
        )
    assert stored_worker is not None
    assert stored_worker.lifecycle_state is WorkerLifecycleState.AVAILABLE


@pytest.mark.asyncio
async def test_worker_control_selects_provider_without_codex_dependency(
    worker_database: ServiceFixture,
) -> None:
    fixture = worker_database
    _, worker, worker_context, _ = await register_available_worker(
        fixture, provider_identifier="codex"
    )
    execution = await disconnected_execution(fixture)
    provider = FakeExecutionProvider()
    service = WorkerControlService(providers=ExecutionProviderRegistry((provider,)))
    started_at = utc_now()
    async with fixture.factory() as session:
        offer = await service.issue_offer(
            session,
            context=operator_context(fixture.context),
            execution_id=execution.execution_id,
            capability_required=WorkerCapability.ENGINEERING_EXECUTE,
            lease_seconds=120,
            now=started_at,
        )
    async with fixture.factory() as session:
        lease = await service.acquire_lease(
            session,
            worker_context=worker_context,
            offer=offer,
            now=started_at + timedelta(seconds=1),
        )
    async with fixture.factory() as session:
        result = await service.execute_with_provider(
            session,
            worker_context=worker_context,
            lease_id=lease.id,
            expected_lease_version=lease.version,
            now=started_at + timedelta(seconds=2),
        )
    assert result.status is ProviderExecutionStatus.SUCCEEDED
    assert len(provider.requests) == 1
    request = provider.requests[0]
    assert request.provider_request_id == lease.id
    assert request.execution_id == execution.execution_id
    assert request.company_id == worker.company_id
    assert request.worker_id == worker.id
    assert request.provider_identifier == "codex"
    assert request.repository_key == "acp-enterprise"
    assert request.instruction_digest == execution.validation_summary.get(
        "instruction_digest", request.instruction_digest
    )
    async with fixture.factory() as session:
        actions = (
            await session.scalars(
                select(AuditRecord.action)
                .where(AuditRecord.resource_id == execution.execution_id)
                .order_by(AuditRecord.occurred_at)
            )
        ).all()
        event_types = (
            await session.scalars(
                select(BusinessEvent.event_type)
                .where(BusinessEvent.entity_id == execution.execution_id)
                .order_by(BusinessEvent.occurred_at)
            )
        ).all()
    assert "engineering.execution_provider_selected" in actions
    assert "engineering.provider_execution_started" in actions
    assert "engineering.provider_execution_completed" in actions
    assert "engineering.execution_provider_selected" in event_types
    assert "engineering.provider_execution_completed" in event_types


@pytest.mark.asyncio
async def test_capability_identity_and_company_mismatches_fail_closed(
    worker_database: ServiceFixture,
) -> None:
    fixture = worker_database
    service, worker, worker_context, _ = await register_available_worker(
        fixture, capabilities=(WorkerCapability.VALIDATION_RUN,)
    )
    execution = await disconnected_execution(fixture)
    now = utc_now()
    async with fixture.factory() as session:
        offer = await service.issue_offer(
            session,
            context=operator_context(fixture.context),
            execution_id=execution.execution_id,
            capability_required=WorkerCapability.ENGINEERING_EXECUTE,
            lease_seconds=60,
            now=now,
        )
    async with fixture.factory() as session:
        with pytest.raises(WorkerLifecycleError):
            await service.acquire_lease(
                session,
                worker_context=worker_context,
                offer=offer,
                now=now + timedelta(seconds=1),
            )
    bad_provider = replace(worker_context, provider_identifier="other-provider")
    async with fixture.factory() as session:
        with pytest.raises(WorkerAuthenticationError):
            await service.record_heartbeat(
                session,
                worker_context=bad_provider,
                health=WorkerHealth.HEALTHY,
            )
    other_company = replace(worker_context, company_id=fixture.other_context.company.id)
    async with fixture.factory() as session:
        with pytest.raises(WorkerNotFoundError):
            await service.record_heartbeat(
                session,
                worker_context=other_company,
                health=WorkerHealth.HEALTHY,
            )
    assert worker.lifecycle_state is WorkerLifecycleState.AVAILABLE


@pytest.mark.asyncio
async def test_active_lease_is_unique_and_versions_fail_closed(
    worker_database: ServiceFixture,
) -> None:
    fixture = worker_database
    service, _, worker_context, _ = await register_available_worker(fixture)
    execution = await disconnected_execution(fixture)
    now = utc_now()
    async with fixture.factory() as session:
        offer = await service.issue_offer(
            session,
            context=operator_context(fixture.context),
            execution_id=execution.execution_id,
            capability_required=WorkerCapability.ENGINEERING_EXECUTE,
            lease_seconds=60,
            now=now,
        )
    async with fixture.factory() as session:
        lease = await service.acquire_lease(
            session,
            worker_context=worker_context,
            offer=offer,
            now=now + timedelta(seconds=1),
        )
    async with fixture.factory() as session:
        with pytest.raises(WorkerLeaseError):
            await service.renew_lease(
                session,
                worker_context=worker_context,
                lease_id=lease.id,
                expected_version=99,
                lease_seconds=60,
                now=now + timedelta(seconds=2),
            )
    async with fixture.factory() as session:
        lease_count = await session.scalar(
            select(func.count(WorkerLease.id)).where(
                WorkerLease.execution_id == execution.execution_id,
                WorkerLease.status == WorkerLeaseStatus.ACTIVE.value,
            )
        )
    assert lease_count == 1


@pytest.mark.asyncio
async def test_expired_lease_is_classified_without_execution(
    worker_database: ServiceFixture,
) -> None:
    fixture = worker_database
    service, _, worker_context, _ = await register_available_worker(fixture)
    execution = await disconnected_execution(fixture)
    now = utc_now()
    async with fixture.factory() as session:
        offer = await service.issue_offer(
            session,
            context=operator_context(fixture.context),
            execution_id=execution.execution_id,
            capability_required=WorkerCapability.ENGINEERING_EXECUTE,
            lease_seconds=30,
            now=now,
        )
    async with fixture.factory() as session:
        lease = await service.acquire_lease(
            session,
            worker_context=worker_context,
            offer=offer,
            now=now + timedelta(seconds=1),
        )
    async with fixture.factory() as session:
        expired = await service.expire_lease(
            session,
            context=operator_context(fixture.context),
            lease_id=lease.id,
            expected_version=lease.version,
            now=lease.expires_at,
        )
    assert expired.status is WorkerLeaseStatus.EXPIRED


@pytest.mark.asyncio
async def test_only_disconnected_structured_result_is_accepted(
    worker_database: ServiceFixture,
) -> None:
    fixture = worker_database
    service, worker, worker_context, _ = await register_available_worker(fixture)
    execution = await disconnected_execution(fixture)
    now = utc_now()
    async with fixture.factory() as session:
        offer = await service.issue_offer(
            session,
            context=operator_context(fixture.context),
            execution_id=execution.execution_id,
            capability_required=WorkerCapability.ENGINEERING_EXECUTE,
            lease_seconds=60,
            now=now,
        )
    async with fixture.factory() as session:
        lease = await service.acquire_lease(
            session,
            worker_context=worker_context,
            offer=offer,
            now=now + timedelta(seconds=1),
        )
    result = WorkerExecutionResult(
        execution_id=execution.execution_id,
        worker_id=worker.id,
        status=WorkerResultStatus.NOT_EXECUTED,
        validation_summary={},
        evidence_summary={"repository_mutated": False, "provider_invoked": False},
        output_references=(),
        failure_classification=WorkerFailureClassification.EXECUTION_NOT_CONNECTED,
    )
    async with fixture.factory() as session:
        stored = await service.accept_result(
            session,
            worker_context=worker_context,
            lease_id=lease.id,
            expected_lease_version=lease.version,
            result=result,
            correlation_id=offer.correlation_id,
            now=now + timedelta(seconds=2),
        )
    assert stored.status is WorkerResultStatus.NOT_EXECUTED
    assert stored.output_references == ()
    with pytest.raises(TypeError):
        stored.evidence_summary["repository_mutated"] = True  # type: ignore[index]
    async with fixture.factory() as session:
        result_count = await session.scalar(
            select(func.count(WorkerResult.id)).where(
                WorkerResult.execution_id == execution.execution_id
            )
        )
    assert result_count == 1

    invalid = replace(result, output_references=("git://forbidden",))
    with pytest.raises(WorkerValidationError):
        async with fixture.factory() as session:
            await service.accept_result(
                session,
                worker_context=worker_context,
                lease_id=lease.id,
                expected_lease_version=lease.version,
                result=invalid,
                correlation_id=offer.correlation_id,
            )
