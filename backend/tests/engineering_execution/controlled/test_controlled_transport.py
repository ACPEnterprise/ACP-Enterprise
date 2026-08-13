from collections.abc import AsyncIterator
from datetime import timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from app.core.config import settings
from app.engineering_control.review.service import EngineeringReviewService
from app.engineering_execution.controlled.contracts import ControlledCommandType
from app.engineering_execution.controlled.repository import (
    ControlledExecutionRepository,
)
from app.engineering_execution.controlled.service import ControlledExecutionService
from app.engineering_execution.models import EngineeringExecution
from app.engineering_execution.service import EngineeringExecutionService
from app.execution_nodes.models import EngineeringExecutionNode
from app.worker_control.contracts import WorkerHealth
from app.worker_control.models import WorkerLease
from app.worker_control.transport.contracts import (
    AuthenticatedMessageEnvelope,
    ControlledExecutionResultMessage,
    ControlledOfferAcquisitionMessage,
    HeartbeatMessage,
    TransportMessageKind,
)
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
    command = await approved_command(fixture, requested_code_changes=True)
    async with fixture.factory() as database:
        execution = await EngineeringExecutionService().request_execution(
            database,
            context=execution_context(fixture.context),
            command_id=command.id,
        )
    now = utc_now()
    async with fixture.factory() as database, database.begin():
        durable_execution = await database.get(
            EngineeringExecution, execution.execution_id
        )
        assert durable_execution is not None
        node = EngineeringExecutionNode(
            company_id=fixture.context.company.id,
            worker_id=worker_session.context.worker_id,
            name="Controlled transport test node",
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
            workspace_id="df9c-test",
            command_type=ControlledCommandType.EXECUTE_CODE,
            payload={
                "node_id": str(node.id),
                "repository_key": command.repository_key,
                "expected_branch": command.expected_branch,
                "expected_head": command.expected_head,
            },
            expires_at=command.expires_at,
            lease_seconds=300,
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
                "starting_head": command.expected_head,
                "head": "b" * 40,
                "commit_sha": "b" * 40,
                "published_commit_sha": "b" * 40,
                "remote_head_before": command.expected_head,
                "mechanically_reconciled": False,
                "clean": True,
                "file_count": 1,
                "file_boundary": ["backend/app/result.py"],
                "repository_mutated": True,
                "validation": {"git diff --check": True},
                "validation_runs": [
                    {
                        "identity": "git diff --check",
                        "argv": ["git", "diff", "--check", "HEAD"],
                        "working_directory": ".",
                        "started_at": (now + timedelta(seconds=2)).isoformat(),
                        "completed_at": completed_at.isoformat(),
                        "duration_ms": 1000,
                        "exit_code": 0,
                        "passed": True,
                        "failure_summary": None,
                        "toolchain": {"python_version": "3.12.13"},
                        "stdout": {
                            "text": "",
                            "truncated": False,
                            "redacted": False,
                        },
                        "stderr": {
                            "text": "",
                            "truncated": False,
                            "redacted": False,
                        },
                    }
                ],
                "validation_environment": {"frontend": "not-required"},
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
    assert package.repository_mutated is True
    assert package.validation_summary["repository_mutated"] is True
    assert package.review.controlled_result_id is not None


@pytest.mark.asyncio
async def test_heartbeat_quarantines_expired_ambiguous_controlled_execution(
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
            workspace_id="expired-test",
            lease_seconds=30,
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
    heartbeat_at = now + timedelta(seconds=32)
    heartbeat = AuthenticatedMessageEnvelope(
        message_id=uuid4(),
        session_id=worker_session.session_id,
        worker_id=worker_session.context.worker_id,
        sequence_number=2,
        sent_at=heartbeat_at,
        kind=TransportMessageKind.HEARTBEAT,
        payload=HeartbeatMessage(health=WorkerHealth.DEGRADED),
        authentication_proof="signed",
        key_version=worker_session.key_version,
    )
    async with fixture.factory() as database:
        await transport.handle_message(database, envelope=heartbeat, now=heartbeat_at)
    async with fixture.factory() as database:
        expired_offer = await ControlledExecutionRepository.get_offer(
            database,
            company_id=fixture.context.company.id,
            offer_id=offer.id,
        )
        lease = await database.get(WorkerLease, expired_offer.lease_id)
        durable_execution = await database.get(
            EngineeringExecution, execution.execution_id
        )
    assert expired_offer is not None and expired_offer.state.value == "expired"
    assert lease is not None and lease.status == "expired"
    assert durable_execution is not None
    # The schema has no reconciliation state; terminal outcome remains unknown.
    # Durable evidence and projections must therefore override this legacy state.
    assert durable_execution.state == "running"
    assert durable_execution.evidence_summary["reconciliation_required"] is True
    assert (
        durable_execution.evidence_summary["reconciliation_reason"]
        == "expired_lease_unresolved_provider_outcome"
    )
