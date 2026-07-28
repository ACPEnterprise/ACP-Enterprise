from collections.abc import AsyncIterator
from datetime import timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.engineering_control.review.service import EngineeringReviewService
from app.engineering_execution.controlled.repository import (
    ControlledExecutionRepository,
)
from app.engineering_execution.controlled.service import ControlledExecutionService
from app.engineering_execution.service import EngineeringExecutionService
from app.worker_control.transport.contracts import (
    AuthenticatedMessageEnvelope,
    ControlledExecutionResultMessage,
    ControlledOfferAcquisitionMessage,
    TransportMessageKind,
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
from tests.worker_control.transport.persistence.test_transport_persistence import (
    established_transport,
)


@pytest_asyncio.fixture
async def controlled_database() -> AsyncIterator[ServiceFixture]:
    engine = create_async_engine(settings.database_url)
    fixture = await seed_service_fixture(
        async_sessionmaker(engine, expire_on_commit=False)
    )
    try:
        yield fixture
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_authenticated_controlled_result_becomes_owner_review(
    controlled_database: ServiceFixture,
) -> None:
    fixture = controlled_database
    transport, worker_session = await established_transport(fixture)
    command = await approved_command(fixture, requested_code_changes=False)
    async with fixture.factory() as database:
        execution = await EngineeringExecutionService().request_execution(
            database,
            context=execution_context(fixture.context),
            command_id=command.id,
        )
    now = utc_now()
    controlled = ControlledExecutionService()
    async with fixture.factory() as database:
        offer = await controlled.prepare_offer(
            database,
            context=execution_context(fixture.context),
            execution_id=execution.execution_id,
            workspace_id="df9c-test",
            now=now,
        )
    acquisition = AuthenticatedMessageEnvelope(
        message_id=uuid4(),
        session_id=worker_session.session_id,
        worker_id=worker_session.context.worker_id,
        sequence_number=1,
        sent_at=now + timedelta(seconds=1),
        kind=TransportMessageKind.CONTROLLED_OFFER_ACQUISITION,
        payload=ControlledOfferAcquisitionMessage(offer_id=offer.id),
        authentication_proof="signed",
        key_version=worker_session.key_version,
    )
    async with fixture.factory() as database:
        await transport.handle_message(database, envelope=acquisition)
    async with fixture.factory() as database:
        acquired = await ControlledExecutionRepository.get_offer(
            database,
            company_id=fixture.context.company.id,
            offer_id=offer.id,
        )
    assert acquired is not None and acquired.lease_id is not None
    completed_at = now + timedelta(seconds=3)
    result = AuthenticatedMessageEnvelope(
        message_id=uuid4(),
        session_id=worker_session.session_id,
        worker_id=worker_session.context.worker_id,
        sequence_number=2,
        sent_at=completed_at,
        kind=TransportMessageKind.CONTROLLED_EXECUTION_RESULT,
        payload=ControlledExecutionResultMessage(
            offer_id=offer.id,
            lease_id=acquired.lease_id,
            outcome="succeeded",
            output={
                "workspace_id": "df9c-test",
                "repository_key": command.repository_key,
                "branch": command.expected_branch,
                "head": command.expected_head,
                "clean": True,
                "file_count": 1,
                "file_boundary": ["README.md"],
                "repository_mutated": False,
            },
            error_classification=None,
            started_at=now + timedelta(seconds=2),
            completed_at=completed_at,
        ),
        authentication_proof="signed",
        key_version=worker_session.key_version,
    )
    async with fixture.factory() as database:
        receipt = await transport.handle_message(database, envelope=result)
    assert receipt.outcome_reference.startswith("controlled_result:")

    async with fixture.factory() as database:
        package = await EngineeringReviewService().prepare(
            database,
            context=fixture.context,
            command_id=command.id,
            now=completed_at + timedelta(seconds=1),
        )
    assert package.result_status == "succeeded"
    assert package.review.provider_identifier == "authenticated-worker"
    assert package.repository_mutated is False
    assert package.review.controlled_result_id is not None
