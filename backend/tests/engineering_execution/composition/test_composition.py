import asyncio
from collections.abc import AsyncIterator
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.engineering_control.models import EngineeringCommand
from app.engineering_execution.composition.contracts import (
    CompositionIntegrityEvidence,
    ProviderAttemptState,
    ProviderProgressPhase,
    ProviderResultDisposition,
    ProviderResultStatus,
)
from app.engineering_execution.composition.errors import (
    CompositionCapabilityError,
    CompositionEvidenceMismatchError,
    CompositionIneligibleError,
    CompositionNotFoundError,
    ResultValidationError,
    StaleAttemptVersionError,
)
from app.engineering_execution.composition.models import (
    CompositionReceipt,
    ExecutionComposition,
    NormalizedProviderResult,
    ProviderExecutionAttempt,
)
from app.engineering_execution.composition.service import (
    ComposeExecution,
    ExecutionCompositionService,
    RecordProviderResult,
    composition_digest,
)
from app.engineering_execution.service import EngineeringExecutionService
from app.execution_providers.contracts import ProviderCapability
from app.execution_providers.registry import ExecutionProviderRegistry
from app.worker_control.contracts import WorkerCapability
from app.worker_control.models import EngineeringWorker
from tests.engineering_control.test_engineering_command_service import (
    ServiceFixture,
    seed_service_fixture,
    utc_now,
)
from tests.engineering_execution.test_engineering_execution import (
    approved_command,
    execution_context,
)
from tests.worker_control.test_worker_control import (
    FakeExecutionProvider,
    operator_context,
    register_available_worker,
)


class FailingBusinessEventService:
    @staticmethod
    def stage(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise RuntimeError("injected event failure")


@pytest_asyncio.fixture
async def composition_database() -> AsyncIterator[ServiceFixture]:
    engine = create_async_engine(settings.database_url)
    fixture = await seed_service_fixture(
        async_sessionmaker(engine, expire_on_commit=False)
    )
    try:
        yield fixture
    finally:
        await engine.dispose()


async def composition_scenario(
    fixture: ServiceFixture,
    *,
    worker_name: str | None = None,
    capabilities: tuple[WorkerCapability, ...] = (
        WorkerCapability.ENGINEERING_EXECUTE,
    ),
    provider_capabilities: tuple[ProviderCapability, ...] = (
        ProviderCapability.ENGINEERING_EXECUTE,
    ),
    instruction: str = "Inspect only the approved execution bridge boundary.",
    requested_code_changes: bool = True,
):
    command = await approved_command(
        fixture,
        instruction=instruction,
        requested_code_changes=requested_code_changes,
    )
    async with fixture.factory() as session:
        execution = await EngineeringExecutionService().request_execution(
            session,
            context=execution_context(fixture.context),
            command_id=command.id,
        )
    worker_service, worker, worker_context, _ = await register_available_worker(
        fixture,
        name=worker_name or f"composition-worker-{uuid4().hex}",
        provider_identifier="codex",
        capabilities=capabilities,
    )
    now = utc_now()
    async with fixture.factory() as session:
        offer = await worker_service.issue_offer(
            session,
            context=operator_context(fixture.context),
            execution_id=execution.execution_id,
            capability_required=WorkerCapability.ENGINEERING_EXECUTE,
            lease_seconds=600,
            now=now,
        )
    async with fixture.factory() as session:
        lease = await worker_service.acquire_lease(
            session,
            worker_context=worker_context,
            offer=offer,
            now=now + timedelta(seconds=1),
        )
    provider = FakeExecutionProvider(
        identifier="codex", capabilities=provider_capabilities
    )
    service = ExecutionCompositionService(
        providers=ExecutionProviderRegistry((provider,))
    )
    compose = ComposeExecution(
        execution_id=execution.execution_id,
        lease_id=lease.id,
        provider_identifier="codex",
        required_capabilities=(ProviderCapability.ENGINEERING_EXECUTE,),
        instruction_digest=command.instruction_digest,
        request_digest=command.request_digest,
        repository_key=command.repository_key,
        expected_branch=command.expected_branch,
        expected_head=command.expected_head,
        approved_code_changes=command.requested_code_changes,
    )
    return service, compose, command, execution, worker, lease, provider


def test_contracts_are_immutable_and_digest_is_deterministic() -> None:
    evidence = CompositionIntegrityEvidence(method="digest_only")
    with pytest.raises(FrozenInstanceError):
        evidence.method = "changed"  # type: ignore[misc]
    assert ProviderAttemptState.QUARANTINED.value == "quarantined"
    source = type(
        "Source",
        (),
        {
            "company_id": uuid4(),
            "command_id": uuid4(),
            "execution_id": uuid4(),
            "worker_id": uuid4(),
            "lease_id": uuid4(),
            "repository_key": "repository",
            "expected_branch": "main",
            "expected_head": "a" * 40,
            "command_instruction_digest": "b" * 64,
            "command_request_digest": "c" * 64,
            "command_expires_at": utc_now() + timedelta(hours=1),
            "lease_expires_at": utc_now() + timedelta(minutes=30),
        },
    )()
    first = composition_digest(
        source=source,
        provider_identifier="provider",
        required=("engineering.execute",),
        effective=("engineering.execute",),
        approved_code_changes=True,
    )
    second = composition_digest(
        source=source,
        provider_identifier="provider",
        required=("engineering.execute",),
        effective=("engineering.execute",),
        approved_code_changes=True,
    )
    assert first == second
    assert len(first) == 64


@pytest.mark.asyncio
async def test_exact_composition_and_receipt_are_atomic_and_idempotent(
    composition_database: ServiceFixture,
) -> None:
    fixture = composition_database
    service, command, _, _, worker, lease, provider = await composition_scenario(
        fixture
    )
    async with fixture.factory() as session:
        first = await service.compose(
            session,
            context=execution_context(fixture.context),
            command=command,
        )
    async with fixture.factory() as session:
        replay = await service.compose(
            session,
            context=execution_context(fixture.context),
            command=command,
        )
        composition_count = await session.scalar(
            select(func.count())
            .select_from(ExecutionComposition)
            .where(ExecutionComposition.execution_id == first.composition.execution_id)
        )
        receipt_count = await session.scalar(
            select(func.count())
            .select_from(CompositionReceipt)
            .where(CompositionReceipt.composition_id == first.composition.id)
        )
    assert replay == first
    assert first.composition.worker_id == worker.id
    assert first.composition.lease_id == lease.id
    assert first.receipt.composition_digest == first.composition.composition_digest
    assert first.receipt.integrity.method == "digest_only"
    assert composition_count == receipt_count == 1
    assert provider.requests == []


@pytest.mark.asyncio
async def test_composition_fails_closed_for_evidence_capability_and_company(
    composition_database: ServiceFixture,
) -> None:
    fixture = composition_database
    service, command, *_ = await composition_scenario(fixture)
    async with fixture.factory() as session:
        with pytest.raises(CompositionEvidenceMismatchError):
            await service.compose(
                session,
                context=execution_context(fixture.context),
                command=replace(command, request_digest="0" * 64),
            )
    async with fixture.factory() as session:
        with pytest.raises(CompositionCapabilityError):
            await service.compose(
                session,
                context=execution_context(fixture.context),
                command=replace(
                    command,
                    required_capabilities=(ProviderCapability.VALIDATION_RUN,),
                ),
            )
    concealed = replace(
        execution_context(fixture.context),
        company=replace(fixture.context.company, id=uuid4()),
    )
    async with fixture.factory() as session:
        with pytest.raises(CompositionNotFoundError):
            await service.compose(session, context=concealed, command=command)
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ExecutionComposition)
                .where(ExecutionComposition.company_id == concealed.company.id)
            )
            == 0
        )


@pytest.mark.asyncio
async def test_invalid_worker_and_expired_lease_fail_before_persistence(
    composition_database: ServiceFixture,
) -> None:
    fixture = composition_database
    service, command, _, _, worker, lease, _ = await composition_scenario(fixture)
    async with fixture.factory() as session, session.begin():
        stored = await session.get(EngineeringWorker, worker.id)
        assert stored is not None
        stored.lifecycle_state = "disabled"
    async with fixture.factory() as session:
        with pytest.raises(CompositionIneligibleError):
            await service.compose(
                session,
                context=execution_context(fixture.context),
                command=command,
            )
    async with fixture.factory() as session, session.begin():
        stored = await session.get(EngineeringWorker, worker.id)
        assert stored is not None
        stored.lifecycle_state = "leased"
    async with fixture.factory() as session:
        with pytest.raises(CompositionIneligibleError):
            await service.compose(
                session,
                context=execution_context(fixture.context),
                command=command,
                now=lease.expires_at + timedelta(seconds=1),
            )


@pytest.mark.asyncio
async def test_expired_approval_cancelled_command_and_provider_mismatch_fail_closed(
    composition_database: ServiceFixture,
) -> None:
    fixture = composition_database

    expired_service, expired_command, approved, *_ = await composition_scenario(fixture)
    async with fixture.factory() as session:
        with pytest.raises(CompositionIneligibleError):
            await expired_service.compose(
                session,
                context=execution_context(fixture.context),
                command=expired_command,
                now=approved.expires_at + timedelta(seconds=1),
            )

    cancelled_service, cancelled_command, approved, *_ = await composition_scenario(
        fixture
    )
    async with fixture.factory() as session, session.begin():
        stored = await session.get(EngineeringCommand, approved.id)
        assert stored is not None
        stored.approval_state = "canceled"
        stored.canceled_at = utc_now()
        stored.canceled_by_user_id = fixture.context.user.id
        stored.cancellation_reason_code = "owner_withdrew"
    async with fixture.factory() as session:
        with pytest.raises(CompositionIneligibleError):
            await cancelled_service.compose(
                session,
                context=execution_context(fixture.context),
                command=cancelled_command,
            )

    mismatch_service, mismatch_command, _, _, worker, *_ = await composition_scenario(
        fixture
    )
    async with fixture.factory() as session, session.begin():
        stored_worker = await session.get(EngineeringWorker, worker.id)
        assert stored_worker is not None
        stored_worker.provider_identifier = "different-provider"
    async with fixture.factory() as session:
        with pytest.raises(CompositionEvidenceMismatchError):
            await mismatch_service.compose(
                session,
                context=execution_context(fixture.context),
                command=mismatch_command,
            )


@pytest.mark.asyncio
async def test_attempt_progress_result_and_quarantine_lifecycle(
    composition_database: ServiceFixture,
) -> None:
    fixture = composition_database
    service, command, *_ = await composition_scenario(fixture)
    context = execution_context(fixture.context)
    async with fixture.factory() as session:
        bundle = await service.compose(session, context=context, command=command)
    async with fixture.factory() as session:
        attempt = await service.prepare_attempt(
            session,
            context=context,
            composition_id=bundle.composition.id,
            idempotency_key=uuid4(),
        )
    async with fixture.factory() as session:
        starting = await service.transition_attempt(
            session,
            context=context,
            attempt_id=attempt.id,
            expected_version=attempt.version,
            to_state=ProviderAttemptState.STARTING,
        )
    async with fixture.factory() as session:
        running = await service.transition_attempt(
            session,
            context=context,
            attempt_id=attempt.id,
            expected_version=starting.version,
            to_state=ProviderAttemptState.RUNNING,
        )
    async with fixture.factory() as session:
        progress = await service.append_progress(
            session,
            context=context,
            attempt_id=attempt.id,
            phase=ProviderProgressPhase.EXECUTING,
            message_code="validation_running",
            summary="Bounded provider-neutral progress.",
            percentage=50,
        )
    assert progress.sequence_number == 1
    async with fixture.factory() as session:
        result = await service.record_result(
            session,
            context=context,
            command=RecordProviderResult(
                attempt_id=attempt.id,
                status=ProviderResultStatus.SUCCEEDED,
                evidence_summary={"evidence": "bounded"},
                validation_summary={"status": "passed"},
                output_references=("evidence://result/1",),
            ),
        )
        stored_attempt = await session.get(ProviderExecutionAttempt, attempt.id)
    assert result.disposition is ProviderResultDisposition.ACCEPTED
    assert result.repository_mutated is False
    assert stored_attempt is not None
    assert stored_attempt.state == ProviderAttemptState.COMPLETED.value
    assert running.started_at == starting.started_at


@pytest.mark.asyncio
async def test_late_result_is_quarantined_and_mutation_claim_rejected(
    composition_database: ServiceFixture,
) -> None:
    fixture = composition_database
    service, command, _, _, _, lease, _ = await composition_scenario(fixture)
    context = execution_context(fixture.context)
    async with fixture.factory() as session:
        bundle = await service.compose(session, context=context, command=command)
    async with fixture.factory() as session:
        attempt = await service.prepare_attempt(
            session,
            context=context,
            composition_id=bundle.composition.id,
            idempotency_key=uuid4(),
        )
    with pytest.raises(ResultValidationError):
        async with fixture.factory() as session:
            await service.record_result(
                session,
                context=context,
                command=RecordProviderResult(
                    attempt_id=attempt.id,
                    status=ProviderResultStatus.SUCCEEDED,
                    evidence_summary={},
                    validation_summary={},
                    output_references=(),
                    repository_mutated=True,
                ),
            )
    async with fixture.factory() as session:
        result = await service.record_result(
            session,
            context=context,
            command=RecordProviderResult(
                attempt_id=attempt.id,
                status=ProviderResultStatus.FAILED,
                evidence_summary={},
                validation_summary={},
                output_references=(),
            ),
            now=lease.expires_at + timedelta(seconds=1),
        )
    assert result.disposition is ProviderResultDisposition.QUARANTINED
    assert result.disposition_reason == "lease_expired"


@pytest.mark.asyncio
async def test_attempt_ordinals_progress_sequences_and_compare_and_swap(
    composition_database: ServiceFixture,
) -> None:
    fixture = composition_database
    service, command, *_ = await composition_scenario(fixture)
    context = execution_context(fixture.context)
    async with fixture.factory() as session:
        bundle = await service.compose(session, context=context, command=command)
    attempts = []
    for _ in range(2):
        async with fixture.factory() as session:
            attempts.append(
                await service.prepare_attempt(
                    session,
                    context=context,
                    composition_id=bundle.composition.id,
                    idempotency_key=uuid4(),
                )
            )
    assert [attempt.attempt_ordinal for attempt in attempts] == [1, 2]
    async with fixture.factory() as session:
        transitioned = await service.transition_attempt(
            session,
            context=context,
            attempt_id=attempts[0].id,
            expected_version=1,
            to_state=ProviderAttemptState.STARTING,
        )
    async with fixture.factory() as session:
        with pytest.raises(StaleAttemptVersionError):
            await service.transition_attempt(
                session,
                context=context,
                attempt_id=attempts[0].id,
                expected_version=1,
                to_state=ProviderAttemptState.RUNNING,
            )
    async with fixture.factory() as session:
        await service.transition_attempt(
            session,
            context=context,
            attempt_id=attempts[0].id,
            expected_version=transitioned.version,
            to_state=ProviderAttemptState.RUNNING,
        )
    for sequence in (1, 2):
        async with fixture.factory() as session:
            event = await service.append_progress(
                session,
                context=context,
                attempt_id=attempts[0].id,
                phase=ProviderProgressPhase.EXECUTING,
                message_code=f"phase_{sequence}",
            )
        assert event.sequence_number == sequence


@pytest.mark.asyncio
async def test_concurrent_attempt_preparation_allocates_unique_ordinals(
    composition_database: ServiceFixture,
) -> None:
    fixture = composition_database
    service, command, *_ = await composition_scenario(fixture)
    context = execution_context(fixture.context)
    async with fixture.factory() as session:
        bundle = await service.compose(session, context=context, command=command)

    async def prepare():
        async with fixture.factory() as session:
            return await service.prepare_attempt(
                session,
                context=context,
                composition_id=bundle.composition.id,
                idempotency_key=uuid4(),
            )

    attempts = await asyncio.gather(prepare(), prepare())
    assert {attempt.attempt_ordinal for attempt in attempts} == {1, 2}


@pytest.mark.asyncio
async def test_event_failure_rolls_back_composition_and_receipt(
    composition_database: ServiceFixture,
) -> None:
    fixture = composition_database
    service, command, *_ = await composition_scenario(fixture)
    failing = ExecutionCompositionService(
        providers=service.providers,
        business_events=FailingBusinessEventService,  # type: ignore[arg-type]
    )
    async with fixture.factory() as session:
        with pytest.raises(RuntimeError, match="injected event failure"):
            await failing.compose(
                session,
                context=execution_context(fixture.context),
                command=command,
            )
    async with fixture.factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ExecutionComposition)
                .where(ExecutionComposition.execution_id == command.execution_id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CompositionReceipt)
                .join(ExecutionComposition)
                .where(ExecutionComposition.execution_id == command.execution_id)
            )
            == 0
        )


@pytest.mark.asyncio
async def test_database_rejects_repository_mutation_claim(
    composition_database: ServiceFixture,
) -> None:
    fixture = composition_database
    service, command, *_ = await composition_scenario(fixture)
    context = execution_context(fixture.context)
    async with fixture.factory() as session:
        bundle = await service.compose(session, context=context, command=command)
    async with fixture.factory() as session:
        attempt = await service.prepare_attempt(
            session,
            context=context,
            composition_id=bundle.composition.id,
            idempotency_key=uuid4(),
        )
    async with fixture.factory() as session:
        result = await service.record_result(
            session,
            context=context,
            command=RecordProviderResult(
                attempt_id=attempt.id,
                status=ProviderResultStatus.FAILED,
                evidence_summary={},
                validation_summary={},
                output_references=(),
            ),
        )
    async with fixture.factory() as session:
        with pytest.raises(IntegrityError):
            async with session.begin():
                stored = await session.get(NormalizedProviderResult, result.id)
                assert stored is not None
                stored.repository_mutated = True


def test_provider_neutral_architecture_has_no_provider_or_network_calls() -> None:
    root = Path(__file__).parents[3] / "app"
    composition_source = "\n".join(
        path.read_text()
        for path in (root / "engineering_execution" / "composition").glob("*.py")
    )
    provider_neutral_source = (
        composition_source + (root / "worker_control" / "service.py").read_text()
    )
    assert "execution_providers.codex" not in provider_neutral_source
    assert ".execute(" not in composition_source
    assert "httpx" not in composition_source
    assert "requests." not in composition_source
    assert "subprocess" not in composition_source
