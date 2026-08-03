import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from app.core.config import settings
from app.engineering_capacity.errors import CapacityUnavailableError
from app.engineering_capacity.models import EngineeringCapacityEvent
from app.engineering_capacity.schemas import (
    CapacityAllocationRequest,
    CapacityBaselineRequest,
    CapacityPolicyUpdate,
    CapacityReconciliationRequest,
    CapacityReleaseRequest,
    CapacityReservationRequest,
    ExistingWorkerCapacitySetup,
    WorkerCapacityRegister,
    WorkerCapacityResponse,
    WorkerStateUpdate,
)
from app.engineering_capacity.service import EngineeringCapacityService
from app.engineering_control.commands import (
    ApproveEngineeringCommand,
    CreateEngineeringCommand,
)
from app.engineering_control.service import EngineeringControlService
from app.worker_control.models import EngineeringWorker
from app.worker_identity.models import WorkerCredential, WorkerIdentity
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.engineering_control.test_engineering_command_service import (
    ServiceFixture,
    seed_service_fixture,
    utc_now,
)


@pytest_asyncio.fixture
async def capacity_database() -> ServiceFixture:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    fixture = await seed_service_fixture(factory)
    try:
        yield fixture
    finally:
        await engine.dispose()


async def approved_command(fixture: ServiceFixture, suffix: str):
    service = EngineeringControlService()
    async with fixture.factory() as session:
        created = await service.create_command(
            session,
            context=fixture.context,
            command=CreateEngineeringCommand(
                command_type="owner_instruction",
                owner_instruction="Perform only the approved bounded engineering milestone.",
                repository_key="acp-enterprise",
                expected_branch="customer-management-v1",
                expected_head="a" * 40,
                requested_code_changes=True,
                expires_at=utc_now() + timedelta(hours=2),
                idempotency_key=f"capacity-command-{suffix}-{uuid4()}",
                execution_boundary={
                    "allowed_repository": "acp-enterprise",
                    "allowed_branch": "customer-management-v1",
                    "expected_head": "a" * 40,
                    "allowed_paths": ["backend/app/**"],
                    "forbidden_paths": [".git/**", ".env*", "**/.env*"],
                    "permitted_operations": [
                        "inspect",
                        "validate",
                        "modify",
                        "commit",
                    ],
                    "validation_requirements": ["git diff --check"],
                },
            ),
        )
    async with fixture.factory() as session:
        return await service.approve_command(
            session,
            context=fixture.context,
            command=ApproveEngineeringCommand(
                command_id=created.id,
                expected_version=created.version,
                instruction_digest=created.instruction_digest,
                request_digest=created.request_digest,
                repository_key=created.repository_key,
                expected_branch=created.expected_branch,
                expected_head=created.expected_head,
                requested_code_changes=created.requested_code_changes,
            ),
        )


async def configured_worker(
    fixture: ServiceFixture, service: EngineeringCapacityService
):
    worker = EngineeringWorker(
        id=uuid4(),
        company_id=fixture.context.company.id,
        provider_identifier=f"capacity-{uuid4()}",
        name=f"Capacity Worker {uuid4()}",
        worker_version="1",
        capabilities=["engineering.execute"],
        lifecycle_state="available",
        registered_by_user_id=fixture.context.user.id,
        registered_at=utc_now(),
    )
    async with fixture.factory() as session, session.begin():
        session.add(worker)
    async with fixture.factory() as session:
        machine = await service.add_machine(
            session,
            context=fixture.context,
            data=CapacityBaselineRequest(machine_label=f"Office Machine {uuid4()}"),
        )
    async with fixture.factory() as session:
        capacity = await service.register_worker_capacity(
            session,
            context=fixture.context,
            data=WorkerCapacityRegister(
                worker_id=worker.id,
                machine_id=machine.id,
                configured_limit=1,
                idempotency_key=f"configure-{worker.id}",
            ),
        )
    async with fixture.factory() as session, session.begin():
        await service.observe_worker_health_in_transaction(
            session,
            company_id=fixture.context.company.id,
            worker_id=worker.id,
            health="healthy",
            observed_at=utc_now(),
        )
    return worker, capacity


async def enrolled_worker(fixture: ServiceFixture) -> EngineeringWorker:
    now = utc_now()
    worker = EngineeringWorker(
        id=uuid4(),
        company_id=fixture.context.company.id,
        provider_identifier=f"trusted-{uuid4()}",
        name=f"Trusted Worker {uuid4()}",
        worker_version="1",
        capabilities=["engineering.execute"],
        lifecycle_state="available",
        registered_by_user_id=fixture.context.user.id,
        registered_at=now,
        last_heartbeat_at=now,
    )
    identity = WorkerIdentity(
        id=uuid4(),
        company_id=fixture.context.company.id,
        name=f"Trusted identity {uuid4()}",
        state="active",
        registered_by_user_id=fixture.context.user.id,
        orchestration_worker_id=worker.id,
        version=1,
        registered_at=now,
        updated_at=now,
    )
    credential = WorkerCredential(
        company_id=fixture.context.company.id,
        identity_id=identity.id,
        version=1,
        state="active",
        verifier="test-verifier",
        verifier_algorithm="ed25519",
        public_key_id=f"test-key-{uuid4()}",
        issued_at=now,
        expires_at=now + timedelta(days=1),
        activated_at=now,
        updated_at=now,
    )
    async with fixture.factory() as session, session.begin():
        session.add(worker)
        await session.flush()
        session.add(identity)
        await session.flush()
        session.add(credential)
    return worker


@pytest.mark.asyncio
async def test_existing_authenticated_worker_can_be_configured_without_enrollment(
    capacity_database: ServiceFixture,
) -> None:
    fixture = capacity_database
    service = EngineeringCapacityService()
    async with fixture.factory() as session:
        await service.update_policy(
            session,
            context=fixture.context,
            data=CapacityPolicyUpdate(
                maximum_concurrent_workstreams=2,
                maximum_per_worker=1,
                reserved_capacity=0,
            ),
        )
    worker = await enrolled_worker(fixture)

    async with fixture.factory() as session:
        before = await service.summary(session, context=fixture.context)
    assert [item.worker_id for item in before.eligible_workers] == [worker.id]
    assert before.configured_capacity == 0

    request = ExistingWorkerCapacitySetup(
        worker_id=worker.id,
        machine_label="Original Office Machine",
        configured_limit=1,
        idempotency_key=f"existing-worker-{worker.id}",
    )
    async with fixture.factory() as session:
        configured = await service.configure_existing_worker(
            session, context=fixture.context, data=request
        )
    async with fixture.factory() as session:
        replay = await service.configure_existing_worker(
            session, context=fixture.context, data=request
        )
        after = await service.summary(session, context=fixture.context)

    assert configured.id == replay.id
    assert configured.machine_label == "Original Office Machine"
    assert configured.health_state == "healthy"
    assert after.configured_capacity == 1
    assert after.available_capacity == 1
    assert after.active_reservations == ()
    assert after.active_allocations == ()
    assert after.eligible_workers[0].capacity_configured is True


@pytest.mark.asyncio
async def test_worker_setup_does_not_wait_for_heartbeat_row_update(
    capacity_database: ServiceFixture,
) -> None:
    fixture = capacity_database
    service = EngineeringCapacityService()
    async with fixture.factory() as session:
        await service.update_policy(
            session,
            context=fixture.context,
            data=CapacityPolicyUpdate(
                maximum_concurrent_workstreams=2,
                maximum_per_worker=1,
                reserved_capacity=0,
            ),
        )
    worker = await enrolled_worker(fixture)

    async with fixture.factory() as heartbeat_session, heartbeat_session.begin():
        await heartbeat_session.execute(
            update(EngineeringWorker)
            .where(EngineeringWorker.id == worker.id)
            .values(last_heartbeat_at=utc_now())
        )

        async def configure() -> WorkerCapacityResponse:
            async with fixture.factory() as session:
                return await service.configure_existing_worker(
                    session,
                    context=fixture.context,
                    data=ExistingWorkerCapacitySetup(
                        worker_id=worker.id,
                        machine_label="Office heartbeat machine",
                        configured_limit=1,
                        idempotency_key=f"heartbeat-safe-{worker.id}",
                    ),
                )

        configured = await asyncio.wait_for(configure(), timeout=2)

    assert configured.worker_id == worker.id
    assert configured.configured_limit == 1


@pytest.mark.asyncio
async def test_default_limit_reservation_allocation_and_idempotent_release(
    capacity_database: ServiceFixture,
) -> None:
    fixture = capacity_database
    service = EngineeringCapacityService()
    async with fixture.factory() as session:
        policy = await service.update_policy(
            session,
            context=fixture.context,
            data=CapacityPolicyUpdate(
                maximum_concurrent_workstreams=1,
                maximum_per_worker=1,
                reserved_capacity=0,
            ),
        )
    assert policy.maximum_concurrent_workstreams == 1
    worker, initial = await configured_worker(fixture, service)
    assert initial.configured_limit == 1
    command = await approved_command(fixture, "lifecycle")
    request = CapacityReservationRequest(
        command_id=command.id,
        worker_id=worker.id,
        owner_intent_reference="approved owner start",
        idempotency_key=f"reserve-{command.id}",
    )
    async with fixture.factory() as session:
        reservation = await service.reserve(
            session, context=fixture.context, data=request
        )
    async with fixture.factory() as session:
        replay = await service.reserve(session, context=fixture.context, data=request)
    assert replay.id == reservation.id
    async with fixture.factory() as session:
        allocation = await service.allocate(
            session,
            context=fixture.context,
            data=CapacityAllocationRequest(
                reservation_id=reservation.id,
                idempotency_key=f"allocate-{reservation.id}",
            ),
        )
    async with fixture.factory() as session:
        allocation_replay = await service.allocate(
            session,
            context=fixture.context,
            data=CapacityAllocationRequest(
                reservation_id=reservation.id,
                idempotency_key=f"allocate-{reservation.id}",
            ),
        )
    assert allocation_replay.id == allocation.id
    async with fixture.factory() as session:
        before_reconciliation = await service.summary(session, context=fixture.context)
    async with fixture.factory() as session:
        held = await service.mark_worker_reconciliation_required(
            session,
            context=fixture.context,
            worker_id=worker.id,
            data=WorkerStateUpdate(
                expected_version=before_reconciliation.workers[0].version,
                reason="worker disconnected during assignment",
            ),
        )
    assert held.operational_state == "reconciliation_required"
    assert held.allocated_capacity == 1
    async with fixture.factory() as session:
        allocation = await service.reconcile(
            session,
            context=fixture.context,
            allocation_id=allocation.id,
            data=CapacityReconciliationRequest(
                resolution="confirmed_active",
                reason="authoritative execution evidence confirms active",
                expected_version=allocation.version + 1,
                idempotency_key=f"reconcile-{allocation.id}",
            ),
        )
    async with fixture.factory() as session:
        released = await service.release_allocation(
            session,
            context=fixture.context,
            allocation_id=allocation.id,
            data=CapacityReleaseRequest(
                idempotency_key=f"release-{allocation.id}",
                reason="validated completion",
                expected_version=allocation.version,
            ),
        )
    async with fixture.factory() as session:
        replay_release = await service.release_allocation(
            session,
            context=fixture.context,
            allocation_id=allocation.id,
            data=CapacityReleaseRequest(
                idempotency_key=f"release-replay-{allocation.id}",
                reason="validated completion",
                expected_version=allocation.version,
            ),
        )
        summary = await service.summary(session, context=fixture.context)
    assert released.status == replay_release.status == "released"
    assert summary.available_capacity == 1
    assert summary.allocated_capacity == 0


@pytest.mark.asyncio
async def test_system_limit_and_concurrent_requests_fail_closed(
    capacity_database: ServiceFixture,
) -> None:
    fixture = capacity_database
    service = EngineeringCapacityService()
    async with fixture.factory() as session:
        await service.update_policy(
            session,
            context=fixture.context,
            data=CapacityPolicyUpdate(
                maximum_concurrent_workstreams=1,
                maximum_per_worker=1,
                reserved_capacity=0,
            ),
        )
    await configured_worker(fixture, service)
    first, second = await asyncio.gather(
        approved_command(fixture, "first"), approved_command(fixture, "second")
    )

    async def reserve(command_id):
        async with fixture.factory() as session:
            return await service.reserve(
                session,
                context=fixture.context,
                data=CapacityReservationRequest(
                    command_id=command_id,
                    owner_intent_reference="owner start",
                    idempotency_key=f"reserve-{command_id}",
                ),
            )

    outcomes = await asyncio.gather(
        reserve(first.id), reserve(second.id), return_exceptions=True
    )
    assert sum(not isinstance(item, Exception) for item in outcomes) == 1
    assert sum(isinstance(item, CapacityUnavailableError) for item in outcomes) == 1


def worker_projection(
    *, state: str, health: str, available: int = 1
) -> WorkerCapacityResponse:
    return WorkerCapacityResponse(
        id=uuid4(),
        worker_id=uuid4(),
        machine_id=uuid4(),
        machine_label="Machine",
        configured_limit=1,
        allocated_capacity=1 - available,
        reserved_capacity=0,
        available_capacity=available,
        operational_state=state,
        health_state=health,
        last_reconciled_at=None,
        version=1,
    )


def test_capacity_decisions_distinguish_policy_health_full_and_reconciliation() -> None:
    service = EngineeringCapacityService()
    assert service._decision(None, ())[0] == "blocked_by_policy"
    policy = type("Policy", (), {"maximum_concurrent_workstreams": 1})()
    assert (
        service._decision(
            policy, (worker_projection(state="offline", health="unknown"),)
        )[0]
        == "blocked_by_worker_health"
    )
    assert (
        service._decision(
            policy,
            (worker_projection(state="occupied", health="healthy", available=0),),
        )[0]
        == "waiting_for_capacity"
    )
    assert (
        service._decision(
            policy,
            (
                worker_projection(
                    state="reconciliation_required", health="healthy", available=0
                ),
            ),
        )[0]
        == "reconciliation_required"
    )
    assert (
        service._decision(
            policy, (worker_projection(state="available", health="healthy"),)
        )[0]
        == "capacity_available"
    )


@pytest.mark.asyncio
async def test_capacity_events_are_company_scoped_and_append_only(
    capacity_database: ServiceFixture,
) -> None:
    fixture = capacity_database
    service = EngineeringCapacityService()
    async with fixture.factory() as session:
        await service.update_policy(
            session,
            context=fixture.context,
            data=CapacityPolicyUpdate(
                maximum_concurrent_workstreams=1,
                maximum_per_worker=1,
                reserved_capacity=0,
            ),
        )
    async with fixture.factory() as session:
        own = (
            await session.scalars(
                select(EngineeringCapacityEvent).where(
                    EngineeringCapacityEvent.company_id == fixture.context.company.id
                )
            )
        ).all()
        other = (
            await session.scalars(
                select(EngineeringCapacityEvent).where(
                    EngineeringCapacityEvent.company_id
                    == fixture.other_context.company.id
                )
            )
        ).all()
    assert [event.event_type for event in own] == ["capacity.policy_updated"]
    assert other == []
