from collections.abc import AsyncIterator
from datetime import timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.engineering_execution.composition.contracts import (
    ProviderAttemptState,
    ProviderProgressPhase,
    ProviderResultStatus,
)
from app.engineering_execution.composition.models import ProviderExecutionAttempt
from app.engineering_execution.composition.service import (
    ComposeExecution,
    ExecutionCompositionService,
)
from app.engineering_execution.service import EngineeringExecutionService
from app.execution_providers.contracts import ProviderCapability
from app.execution_providers.registry import ExecutionProviderRegistry
from app.worker_control.contracts import WorkerCapability
from app.worker_control.service import WorkerControlService
from app.worker_control.transport.contracts import (
    AuthenticatedMessageEnvelope,
    CancellationAcknowledgementMessage,
    CompositionAcknowledgementMessage,
    CompositionFetchMessage,
    ProviderProgressMessage,
    ProviderResultMessage,
    TransportMessageKind,
)
from app.worker_control.transport.errors import TransportMessageError
from app.worker_control.transport.persistence.models import (
    WorkerTransportReceipt,
    WorkerTransportSession,
)
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
)
from tests.worker_control.transport.persistence.test_transport_persistence import (
    established_transport,
)


@pytest_asyncio.fixture
async def composition_transport_database() -> AsyncIterator[ServiceFixture]:
    engine = create_async_engine(settings.database_url)
    fixture = await seed_service_fixture(
        async_sessionmaker(engine, expire_on_commit=False)
    )
    try:
        yield fixture
    finally:
        await engine.dispose()


async def prepared_delivery(fixture: ServiceFixture):
    transport, session = await established_transport(fixture)
    command = await approved_command(fixture)
    async with fixture.factory() as database:
        execution = await EngineeringExecutionService().request_execution(
            database,
            context=execution_context(fixture.context),
            command_id=command.id,
        )
    control = WorkerControlService()
    now = utc_now()
    async with fixture.factory() as database:
        offer = await control.issue_offer(
            database,
            context=operator_context(fixture.context),
            execution_id=execution.execution_id,
            capability_required=WorkerCapability.ENGINEERING_EXECUTE,
            lease_seconds=600,
            now=now,
        )
    async with fixture.factory() as database:
        lease = await control.acquire_lease(
            database,
            worker_context=session.context,
            offer=offer,
            now=now + timedelta(seconds=1),
        )
    compositions = ExecutionCompositionService(
        providers=ExecutionProviderRegistry(
            (
                FakeExecutionProvider(
                    identifier=session.context.provider_identifier,
                ),
            )
        )
    )
    async with fixture.factory() as database:
        bundle = await compositions.compose(
            database,
            context=execution_context(fixture.context),
            command=ComposeExecution(
                execution_id=execution.execution_id,
                lease_id=lease.id,
                provider_identifier=session.context.provider_identifier,
                required_capabilities=(ProviderCapability.ENGINEERING_EXECUTE,),
                instruction_digest=command.instruction_digest,
                request_digest=command.request_digest,
                repository_key=command.repository_key,
                expected_branch=command.expected_branch,
                expected_head=command.expected_head,
                approved_code_changes=command.requested_code_changes,
            ),
        )
    async with fixture.factory() as database:
        attempt = await compositions.prepare_attempt(
            database,
            context=execution_context(fixture.context),
            composition_id=bundle.composition.id,
            idempotency_key=uuid4(),
        )
    async with fixture.factory() as database:
        starting = await compositions.transition_attempt(
            database,
            context=execution_context(fixture.context),
            attempt_id=attempt.id,
            expected_version=attempt.version,
            to_state=ProviderAttemptState.STARTING,
        )
    async with fixture.factory() as database:
        attempt = await compositions.transition_attempt(
            database,
            context=execution_context(fixture.context),
            attempt_id=attempt.id,
            expected_version=starting.version,
            to_state=ProviderAttemptState.RUNNING,
        )
    return transport, session, bundle, attempt, lease


def envelope(session, sequence, kind, payload, *, message_id=None):
    return AuthenticatedMessageEnvelope(
        message_id=message_id or uuid4(),
        session_id=session.session_id,
        worker_id=session.context.worker_id,
        sequence_number=sequence,
        sent_at=utc_now(),
        kind=kind,
        payload=payload,
        authentication_proof="signed",
        key_version=session.key_version,
    )


@pytest.mark.asyncio
async def test_authenticated_composition_delivery_progress_and_result(
    composition_transport_database: ServiceFixture,
) -> None:
    fixture = composition_transport_database
    transport, session, bundle, attempt, lease = await prepared_delivery(fixture)
    fetch = envelope(
        session, 1, TransportMessageKind.COMPOSITION_FETCH, CompositionFetchMessage()
    )
    async with fixture.factory() as database:
        receipt = await transport.handle_message(database, envelope=fetch)
    async with fixture.factory() as database:
        duplicate = await transport.handle_message(database, envelope=fetch)
    assert receipt.outcome_reference == f"composition:{bundle.composition.id}"
    assert duplicate.duplicate is True

    acknowledgement = envelope(
        session,
        2,
        TransportMessageKind.COMPOSITION_ACKNOWLEDGEMENT,
        CompositionAcknowledgementMessage(
            composition_id=bundle.composition.id,
            composition_digest=bundle.composition.composition_digest,
            instruction_digest=bundle.composition.instruction_digest,
            request_digest=bundle.composition.request_digest,
        ),
    )
    async with fixture.factory() as database:
        await transport.handle_message(database, envelope=acknowledgement)

    progress = envelope(
        session,
        3,
        TransportMessageKind.PROVIDER_PROGRESS,
        ProviderProgressMessage(
            attempt_id=attempt.id,
            lease_id=lease.id,
            composition_digest=bundle.composition.composition_digest,
            instruction_digest=bundle.composition.instruction_digest,
            request_digest=bundle.composition.request_digest,
            phase=ProviderProgressPhase.EXECUTING,
            message_code="simulated_progress",
            summary="Provider-neutral simulated progress.",
            percentage=25,
        ),
    )
    async with fixture.factory() as database:
        progress_receipt = await transport.handle_message(database, envelope=progress)
    assert progress_receipt.outcome_reference.startswith("provider_progress:")

    async with fixture.factory() as database, database.begin():
        stored_attempt = await database.get(ProviderExecutionAttempt, attempt.id)
        assert stored_attempt is not None
        stored_attempt.cancellation_requested_at = utc_now()
    cancellation = envelope(
        session,
        4,
        TransportMessageKind.CANCELLATION_ACKNOWLEDGEMENT,
        CancellationAcknowledgementMessage(
            attempt_id=attempt.id,
            lease_id=lease.id,
            expected_version=attempt.version,
            composition_digest=bundle.composition.composition_digest,
        ),
    )
    async with fixture.factory() as database:
        cancellation_receipt = await transport.handle_message(
            database, envelope=cancellation
        )
    assert cancellation_receipt.outcome_reference.startswith(
        "cancellation_acknowledged:"
    )

    result = envelope(
        session,
        5,
        TransportMessageKind.PROVIDER_RESULT,
        ProviderResultMessage(
            attempt_id=attempt.id,
            lease_id=lease.id,
            composition_digest=bundle.composition.composition_digest,
            instruction_digest=bundle.composition.instruction_digest,
            request_digest=bundle.composition.request_digest,
            status=ProviderResultStatus.SUCCEEDED,
            evidence_summary={"simulation": True},
            validation_summary={"status": "not_executed"},
            output_references=("evidence://simulation",),
            repository_mutated=False,
        ),
    )
    async with fixture.factory() as database:
        result_receipt = await transport.handle_message(database, envelope=result)
    assert result_receipt.outcome_reference.endswith(":accepted")


@pytest.mark.asyncio
async def test_altered_evidence_rolls_back_sequence_and_receipt(
    composition_transport_database: ServiceFixture,
) -> None:
    fixture = composition_transport_database
    transport, session, bundle, *_ = await prepared_delivery(fixture)
    invalid = envelope(
        session,
        1,
        TransportMessageKind.COMPOSITION_ACKNOWLEDGEMENT,
        CompositionAcknowledgementMessage(
            composition_id=bundle.composition.id,
            composition_digest="0" * 64,
            instruction_digest=bundle.composition.instruction_digest,
            request_digest=bundle.composition.request_digest,
        ),
    )
    with pytest.raises(TransportMessageError):
        async with fixture.factory() as database:
            await transport.handle_message(database, envelope=invalid)
    async with fixture.factory() as database:
        stored_session = await database.get(WorkerTransportSession, session.session_id)
        stored_receipt = await database.get(WorkerTransportReceipt, invalid.message_id)
    assert stored_session is not None
    assert stored_session.next_sequence == 1
    assert stored_receipt is None


@pytest.mark.asyncio
async def test_expired_lease_result_is_preserved_as_quarantined(
    composition_transport_database: ServiceFixture,
) -> None:
    fixture = composition_transport_database
    transport, session, bundle, attempt, lease = await prepared_delivery(fixture)
    received_at = lease.expires_at + timedelta(seconds=1)
    result = AuthenticatedMessageEnvelope(
        message_id=uuid4(),
        session_id=session.session_id,
        worker_id=session.context.worker_id,
        sequence_number=1,
        sent_at=received_at,
        kind=TransportMessageKind.PROVIDER_RESULT,
        payload=ProviderResultMessage(
            attempt_id=attempt.id,
            lease_id=lease.id,
            composition_digest=bundle.composition.composition_digest,
            instruction_digest=bundle.composition.instruction_digest,
            request_digest=bundle.composition.request_digest,
            status=ProviderResultStatus.FAILED,
            evidence_summary={"late": True},
            validation_summary={},
            output_references=(),
            repository_mutated=False,
        ),
        authentication_proof="signed",
        key_version=session.key_version,
    )
    async with fixture.factory() as database:
        receipt = await transport.handle_message(
            database, envelope=result, now=received_at
        )
    assert receipt.outcome_reference.endswith(":quarantined")
