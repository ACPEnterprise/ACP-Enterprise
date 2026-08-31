import asyncio
from collections.abc import AsyncIterator
from dataclasses import FrozenInstanceError, dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.platform.permissions.models  # noqa: F401
from app.core.config import settings
from app.engineering_control.models import EngineeringCommand
from app.engineering_control.records import (
    AppendEngineeringCommandEvent,
    CreateEngineeringCommand,
    EngineeringApprovalState,
    EngineeringCommandQueryResult,
    EngineeringExecutionState,
    EngineeringMutationStatus,
)
from app.engineering_control.repository import EngineeringCommandRepository
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.users.models import User


@dataclass(frozen=True)
class EngineeringFixture:
    factory: async_sessionmaker[AsyncSession]
    company_id: UUID
    user_id: UUID
    other_company_id: UUID
    other_user_id: UUID


@pytest_asyncio.fixture
async def engineering_database() -> AsyncIterator[EngineeringFixture]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    company_id, other_company_id = uuid4(), uuid4()
    user_id, other_user_id = uuid4(), uuid4()
    now = datetime.now(timezone.utc)
    async with factory() as session, session.begin():
        session.add_all(
            [
                User(
                    id=user_id,
                    normalized_email=f"{uuid4().hex}@example.com",
                    first_name="Owner",
                    last_name="One",
                    display_name="Owner One",
                    status="active",
                ),
                User(
                    id=other_user_id,
                    normalized_email=f"{uuid4().hex}@example.com",
                    first_name="Owner",
                    last_name="Two",
                    display_name="Owner Two",
                    status="active",
                ),
                Company(
                    id=company_id,
                    name="Engineering Company",
                    code=f"E{uuid4().hex[:8].upper()}",
                    status="active",
                    timezone="America/New_York",
                ),
                Company(
                    id=other_company_id,
                    name="Other Engineering Company",
                    code=f"O{uuid4().hex[:8].upper()}",
                    status="active",
                    timezone="America/New_York",
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                Membership(
                    user_id=user_id,
                    company_id=company_id,
                    status="active",
                    accepted_at=now,
                    has_all_branch_access=True,
                ),
                Membership(
                    user_id=other_user_id,
                    company_id=other_company_id,
                    status="active",
                    accepted_at=now,
                    has_all_branch_access=True,
                ),
            ]
        )
    fixture = EngineeringFixture(
        factory, company_id, user_id, other_company_id, other_user_id
    )
    try:
        yield fixture
    finally:
        await engine.dispose()


def command_input(
    fixture: EngineeringFixture,
    *,
    other: bool = False,
    idempotency_key: str | None = None,
    created_at: datetime | None = None,
) -> CreateEngineeringCommand:
    occurred_at = created_at or datetime.now(timezone.utc)
    return CreateEngineeringCommand(
        company_id=fixture.other_company_id if other else fixture.company_id,
        requested_by_user_id=fixture.other_user_id if other else fixture.user_id,
        command_type="owner_instruction",
        owner_instruction="Inspect the approved engineering boundary.",
        instruction_digest=uuid4().hex,
        repository_key="acp-enterprise",
        expected_branch="customer-management-v1",
        expected_head="a" * 40,
        requested_code_changes=True,
        idempotency_key=idempotency_key or uuid4().hex,
        request_digest=uuid4().hex,
        expires_at=occurred_at + timedelta(hours=1),
        created_at=occurred_at,
    )


@pytest.mark.asyncio
async def test_command_creation_retrieval_concealment_and_immutable_record(
    engineering_database: EngineeringFixture,
) -> None:
    fixture = engineering_database
    async with fixture.factory() as session, session.begin():
        record = await EngineeringCommandRepository.create_command(
            session, command=command_input(fixture)
        )

    assert record.ecid.startswith(f"ECID-{record.created_at.year}-")
    assert record.approval_state is EngineeringApprovalState.AWAITING_APPROVAL
    assert record.execution_state is EngineeringExecutionState.EXECUTION_NOT_CONNECTED
    assert record.version == 1
    with pytest.raises(FrozenInstanceError):
        record.ecid = "ECID-2026-999999"  # type: ignore[misc]

    async with fixture.factory() as session:
        by_id = await EngineeringCommandRepository.get_command(
            session, company_id=fixture.company_id, command_id=record.id
        )
        by_ecid = await EngineeringCommandRepository.get_command_by_ecid(
            session, company_id=fixture.company_id, ecid=record.ecid
        )
        by_key = await EngineeringCommandRepository.get_command_by_idempotency_key(
            session,
            company_id=fixture.company_id,
            idempotency_key=record.idempotency_key,
        )
        concealed = await EngineeringCommandRepository.get_command(
            session, company_id=fixture.other_company_id, command_id=record.id
        )
    assert by_id == by_ecid == by_key == record
    assert concealed is None


@pytest.mark.asyncio
async def test_company_idempotency_and_actor_ownership_constraints(
    engineering_database: EngineeringFixture,
) -> None:
    fixture = engineering_database
    key = uuid4().hex
    async with fixture.factory() as session, session.begin():
        await EngineeringCommandRepository.create_command(
            session, command=command_input(fixture, idempotency_key=key)
        )
    async with fixture.factory() as session:
        with pytest.raises(IntegrityError):
            async with session.begin():
                await EngineeringCommandRepository.create_command(
                    session, command=command_input(fixture, idempotency_key=key)
                )
    async with fixture.factory() as session, session.begin():
        other = await EngineeringCommandRepository.create_command(
            session,
            command=command_input(fixture, other=True, idempotency_key=key),
        )
    assert other.company_id == fixture.other_company_id

    invalid = command_input(fixture)
    invalid = CreateEngineeringCommand(
        **{**invalid.__dict__, "requested_by_user_id": fixture.other_user_id}
    )
    async with fixture.factory() as session:
        with pytest.raises(IntegrityError):
            async with session.begin():
                await EngineeringCommandRepository.create_command(
                    session, command=invalid
                )


@pytest.mark.asyncio
async def test_ecid_allocation_is_global_unique_and_concurrency_safe(
    engineering_database: EngineeringFixture,
) -> None:
    fixture = engineering_database
    occurred_at = datetime.now(timezone.utc)

    async def allocate(other: bool) -> str:
        async with fixture.factory() as session, session.begin():
            record = await EngineeringCommandRepository.create_command(
                session,
                command=command_input(fixture, other=other, created_at=occurred_at),
            )
            return record.ecid

    identifiers = await asyncio.gather(
        *(allocate(index % 2 == 1) for index in range(8))
    )

    assert len(set(identifiers)) == 8
    assert all(
        identifier.startswith(f"ECID-{occurred_at.year}-") for identifier in identifiers
    )


@pytest.mark.asyncio
async def test_deterministic_listing_locking_and_limit_validation(
    engineering_database: EngineeringFixture,
) -> None:
    fixture = engineering_database
    now = datetime.now(timezone.utc)
    async with fixture.factory() as session, session.begin():
        first = await EngineeringCommandRepository.create_command(
            session, command=command_input(fixture, created_at=now)
        )
        second = await EngineeringCommandRepository.create_command(
            session,
            command=command_input(fixture, created_at=now + timedelta(microseconds=1)),
        )
    async with fixture.factory() as session, session.begin():
        listed = await EngineeringCommandRepository.list_commands(
            session, company_id=fixture.company_id
        )
        locked = await EngineeringCommandRepository.get_command_for_update(
            session, company_id=fixture.company_id, command_id=first.id
        )
    assert isinstance(listed, EngineeringCommandQueryResult)
    assert [item.id for item in listed.items[:2]] == [second.id, first.id]
    assert listed.total_count == 2
    assert locked == first
    async with fixture.factory() as session:
        with pytest.raises(ValueError):
            await EngineeringCommandRepository.list_commands(
                session, company_id=fixture.company_id, limit=0
            )
        with pytest.raises(ValueError):
            await EngineeringCommandRepository.list_commands(
                session, company_id=fixture.company_id, offset=-1
            )
        with pytest.raises(ValueError):
            await EngineeringCommandRepository.list_commands(
                session, company_id=fixture.company_id, limit=201
            )


@pytest.mark.asyncio
async def test_paginated_listing_filters_counts_and_orders_authoritatively(
    engineering_database: EngineeringFixture,
) -> None:
    fixture = engineering_database
    now = datetime.now(timezone.utc)
    async with fixture.factory() as session, session.begin():
        records = [
            await EngineeringCommandRepository.create_command(
                session,
                command=command_input(
                    fixture,
                    created_at=now if index < 2 else now - timedelta(seconds=index),
                ),
            )
            for index in range(5)
        ]
        other = await EngineeringCommandRepository.create_command(
            session, command=command_input(fixture, other=True, created_at=now)
        )
    async with fixture.factory() as session, session.begin():
        approved = await EngineeringCommandRepository.approve_command(
            session,
            company_id=fixture.company_id,
            command_id=records[2].id,
            expected_version=1,
            approved_by_user_id=fixture.user_id,
            approved_at=now + timedelta(seconds=1),
        )
    assert approved.status is EngineeringMutationStatus.APPLIED

    async with fixture.factory() as session:
        first_page = await EngineeringCommandRepository.list_commands(
            session, company_id=fixture.company_id, offset=0, limit=2
        )
        second_page = await EngineeringCommandRepository.list_commands(
            session, company_id=fixture.company_id, offset=2, limit=2
        )
        beyond = await EngineeringCommandRepository.list_commands(
            session, company_id=fixture.company_id, offset=20, limit=2
        )
        filtered = await EngineeringCommandRepository.list_commands(
            session,
            company_id=fixture.company_id,
            approval_state=EngineeringApprovalState.APPROVED,
            offset=0,
            limit=10,
        )
        empty_other_filter = await EngineeringCommandRepository.list_commands(
            session,
            company_id=fixture.other_company_id,
            approval_state=EngineeringApprovalState.APPROVED,
        )

    expected = sorted(
        records, key=lambda record: (record.created_at, record.id), reverse=True
    )
    assert [record.id for record in first_page.items] == [
        record.id for record in expected[:2]
    ]
    assert [record.id for record in second_page.items] == [
        record.id for record in expected[2:4]
    ]
    assert first_page.total_count == second_page.total_count == 5
    assert beyond.items == ()
    assert beyond.total_count == 5
    assert filtered.items == (approved.record,)
    assert filtered.total_count == 1
    assert empty_other_filter.items == ()
    assert empty_other_filter.total_count == 0
    assert other.id not in {record.id for record in first_page.items}


@pytest.mark.asyncio
async def test_approval_compare_and_swap_and_result_classification(
    engineering_database: EngineeringFixture,
) -> None:
    fixture = engineering_database
    now = datetime.now(timezone.utc)
    async with fixture.factory() as session, session.begin():
        original = await EngineeringCommandRepository.create_command(
            session, command=command_input(fixture, created_at=now)
        )
    async with fixture.factory() as session, session.begin():
        concealed = await EngineeringCommandRepository.approve_command(
            session,
            company_id=fixture.other_company_id,
            command_id=original.id,
            expected_version=1,
            approved_by_user_id=fixture.other_user_id,
            approved_at=now + timedelta(seconds=1),
        )
    assert concealed.status is EngineeringMutationStatus.NOT_FOUND

    approved_at = now + timedelta(seconds=2)
    async with fixture.factory() as session, session.begin():
        applied = await EngineeringCommandRepository.approve_command(
            session,
            company_id=fixture.company_id,
            command_id=original.id,
            expected_version=1,
            approved_by_user_id=fixture.user_id,
            approved_at=approved_at,
        )
    assert applied.status is EngineeringMutationStatus.APPLIED
    assert applied.record is not None
    approved = applied.record
    assert approved.approval_state is EngineeringApprovalState.APPROVED
    assert approved.approved_by_user_id == fixture.user_id
    assert approved.approved_at == approved_at
    assert approved.version == 2
    assert approved.updated_at == approved_at
    assert approved.execution_state is EngineeringExecutionState.EXECUTION_NOT_CONNECTED
    for field_name in (
        "ecid",
        "owner_instruction",
        "instruction_digest",
        "repository_key",
        "expected_branch",
        "expected_head",
        "requested_code_changes",
        "idempotency_key",
        "request_digest",
        "result_reference",
    ):
        assert getattr(approved, field_name) == getattr(original, field_name)

    async with fixture.factory() as session, session.begin():
        stale = await EngineeringCommandRepository.approve_command(
            session,
            company_id=fixture.company_id,
            command_id=original.id,
            expected_version=1,
            approved_by_user_id=fixture.user_id,
            approved_at=approved_at,
        )
        ineligible = await EngineeringCommandRepository.approve_command(
            session,
            company_id=fixture.company_id,
            command_id=original.id,
            expected_version=2,
            approved_by_user_id=fixture.user_id,
            approved_at=approved_at,
        )
    assert stale.status is EngineeringMutationStatus.STALE_VERSION
    assert ineligible.status is EngineeringMutationStatus.INELIGIBLE_STATE


@pytest.mark.asyncio
async def test_concurrent_approvals_allow_one_winner(
    engineering_database: EngineeringFixture,
) -> None:
    fixture = engineering_database
    now = datetime.now(timezone.utc)
    async with fixture.factory() as session, session.begin():
        command = await EngineeringCommandRepository.create_command(
            session, command=command_input(fixture, created_at=now)
        )

    async def approve() -> EngineeringMutationStatus:
        async with fixture.factory() as session, session.begin():
            result = await EngineeringCommandRepository.approve_command(
                session,
                company_id=fixture.company_id,
                command_id=command.id,
                expected_version=1,
                approved_by_user_id=fixture.user_id,
                approved_at=now + timedelta(seconds=1),
            )
            return result.status

    statuses = await asyncio.gather(approve(), approve())
    assert statuses.count(EngineeringMutationStatus.APPLIED) == 1
    assert statuses.count(EngineeringMutationStatus.STALE_VERSION) == 1


@pytest.mark.asyncio
async def test_approval_fails_closed_after_command_expiration(
    engineering_database: EngineeringFixture,
) -> None:
    fixture = engineering_database
    now = datetime.now(timezone.utc)
    async with fixture.factory() as session, session.begin():
        command = await EngineeringCommandRepository.create_command(
            session, command=command_input(fixture, created_at=now)
        )
        result = await EngineeringCommandRepository.approve_command(
            session,
            company_id=fixture.company_id,
            command_id=command.id,
            expected_version=1,
            approved_by_user_id=fixture.user_id,
            approved_at=command.expires_at,
        )
    assert result.status is EngineeringMutationStatus.INELIGIBLE_STATE


@pytest.mark.asyncio
async def test_cancellation_compare_and_swap_and_competing_transition(
    engineering_database: EngineeringFixture,
) -> None:
    fixture = engineering_database
    now = datetime.now(timezone.utc)
    async with fixture.factory() as session, session.begin():
        command = await EngineeringCommandRepository.create_command(
            session, command=command_input(fixture, created_at=now)
        )
    canceled_at = now + timedelta(seconds=1)
    async with fixture.factory() as session, session.begin():
        applied = await EngineeringCommandRepository.cancel_command(
            session,
            company_id=fixture.company_id,
            command_id=command.id,
            expected_version=1,
            canceled_by_user_id=fixture.user_id,
            canceled_at=canceled_at,
            cancellation_reason_code="owner_requested",
        )
    assert applied.status is EngineeringMutationStatus.APPLIED
    assert applied.record is not None
    assert applied.record.approval_state is EngineeringApprovalState.CANCELED
    assert applied.record.canceled_by_user_id == fixture.user_id
    assert applied.record.canceled_at == canceled_at
    assert applied.record.cancellation_reason_code == "owner_requested"
    assert applied.record.version == 2
    assert (
        applied.record.execution_state
        is EngineeringExecutionState.EXECUTION_NOT_CONNECTED
    )
    async with fixture.factory() as session, session.begin():
        stale = await EngineeringCommandRepository.cancel_command(
            session,
            company_id=fixture.company_id,
            command_id=command.id,
            expected_version=1,
            canceled_by_user_id=fixture.user_id,
            canceled_at=canceled_at,
            cancellation_reason_code="owner_requested",
        )
        terminal = await EngineeringCommandRepository.cancel_command(
            session,
            company_id=fixture.company_id,
            command_id=command.id,
            expected_version=2,
            canceled_by_user_id=fixture.user_id,
            canceled_at=canceled_at,
            cancellation_reason_code="owner_requested",
        )
    assert stale.status is EngineeringMutationStatus.STALE_VERSION
    assert terminal.status is EngineeringMutationStatus.INELIGIBLE_STATE

    async with fixture.factory() as session, session.begin():
        competing = await EngineeringCommandRepository.create_command(
            session, command=command_input(fixture, created_at=now)
        )

    async def approve_or_cancel(approve: bool) -> EngineeringMutationStatus:
        async with fixture.factory() as session, session.begin():
            if approve:
                result = await EngineeringCommandRepository.approve_command(
                    session,
                    company_id=fixture.company_id,
                    command_id=competing.id,
                    expected_version=1,
                    approved_by_user_id=fixture.user_id,
                    approved_at=now + timedelta(seconds=2),
                )
            else:
                result = await EngineeringCommandRepository.cancel_command(
                    session,
                    company_id=fixture.company_id,
                    command_id=competing.id,
                    expected_version=1,
                    canceled_by_user_id=fixture.user_id,
                    canceled_at=now + timedelta(seconds=2),
                    cancellation_reason_code="owner_requested",
                )
            return result.status

    statuses = await asyncio.gather(approve_or_cancel(True), approve_or_cancel(False))
    assert statuses.count(EngineeringMutationStatus.APPLIED) == 1
    assert statuses.count(EngineeringMutationStatus.STALE_VERSION) == 1


@pytest.mark.asyncio
async def test_expiration_compare_and_swap(
    engineering_database: EngineeringFixture,
) -> None:
    fixture = engineering_database
    now = datetime.now(timezone.utc)
    async with fixture.factory() as session, session.begin():
        command = await EngineeringCommandRepository.create_command(
            session, command=command_input(fixture, created_at=now)
        )
    expired_at = now + timedelta(hours=2)
    async with fixture.factory() as session, session.begin():
        premature = await EngineeringCommandRepository.expire_command(
            session,
            company_id=fixture.company_id,
            command_id=command.id,
            expected_version=1,
            expired_at=now + timedelta(minutes=30),
        )
        concealed = await EngineeringCommandRepository.expire_command(
            session,
            company_id=fixture.other_company_id,
            command_id=command.id,
            expected_version=1,
            expired_at=expired_at,
        )
        applied = await EngineeringCommandRepository.expire_command(
            session,
            company_id=fixture.company_id,
            command_id=command.id,
            expected_version=1,
            expired_at=expired_at,
        )
    assert premature.status is EngineeringMutationStatus.INELIGIBLE_STATE
    assert concealed.status is EngineeringMutationStatus.NOT_FOUND
    assert applied.status is EngineeringMutationStatus.APPLIED
    assert applied.record is not None
    assert applied.record.approval_state is EngineeringApprovalState.EXPIRED
    assert applied.record.version == 2
    assert applied.record.updated_at == expired_at
    assert (
        applied.record.execution_state
        is EngineeringExecutionState.EXECUTION_NOT_CONNECTED
    )
    async with fixture.factory() as session, session.begin():
        stale = await EngineeringCommandRepository.expire_command(
            session,
            company_id=fixture.company_id,
            command_id=command.id,
            expected_version=1,
            expired_at=expired_at,
        )
        terminal = await EngineeringCommandRepository.expire_command(
            session,
            company_id=fixture.company_id,
            command_id=command.id,
            expected_version=2,
            expired_at=expired_at,
        )
    assert stale.status is EngineeringMutationStatus.STALE_VERSION
    assert terminal.status is EngineeringMutationStatus.INELIGIBLE_STATE


@pytest.mark.asyncio
async def test_database_command_constraints(
    engineering_database: EngineeringFixture,
) -> None:
    fixture = engineering_database
    base = command_input(fixture)
    invalid_values = (
        {"expected_head": "A" * 40},
        {"expires_at": base.created_at},
    )
    for changes in invalid_values:
        invalid = CreateEngineeringCommand(**{**base.__dict__, **changes})
        async with fixture.factory() as session:
            with pytest.raises(IntegrityError):
                async with session.begin():
                    await EngineeringCommandRepository.create_command(
                        session, command=invalid
                    )

    async with fixture.factory() as session:
        entity = EngineeringCommand(
            ecid=f"ECID-{base.created_at.year}-999999",
            company_id=fixture.company_id,
            requested_by_user_id=fixture.user_id,
            command_type=base.command_type,
            owner_instruction=base.owner_instruction,
            instruction_digest=base.instruction_digest,
            repository_key=base.repository_key,
            expected_branch=base.expected_branch,
            expected_head=base.expected_head,
            requested_code_changes=False,
            approval_state="unsupported",
            execution_state="running",
            idempotency_key=uuid4().hex,
            request_digest=uuid4().hex,
            correlation_id=uuid4(),
            expires_at=base.expires_at,
            version=0,
            created_at=base.created_at,
            updated_at=base.created_at,
        )
        session.add(entity)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_event_append_order_uniqueness_and_company_consistency(
    engineering_database: EngineeringFixture,
) -> None:
    fixture = engineering_database
    now = datetime.now(timezone.utc)
    async with fixture.factory() as session, session.begin():
        command = await EngineeringCommandRepository.create_command(
            session, command=command_input(fixture, created_at=now)
        )
        first = await EngineeringCommandRepository.append_event(
            session,
            event=AppendEngineeringCommandEvent(
                company_id=fixture.company_id,
                command_id=command.id,
                ecid=command.ecid,
                instruction_digest=command.instruction_digest,
                event_type="engineering.command_created",
                occurred_at=now,
                correlation_id=command.correlation_id,
                actor_user_id=fixture.user_id,
            ),
        )
        second = await EngineeringCommandRepository.append_event(
            session,
            event=AppendEngineeringCommandEvent(
                company_id=fixture.company_id,
                command_id=command.id,
                ecid=command.ecid,
                instruction_digest=command.instruction_digest,
                event_type="engineering.command_validated",
                occurred_at=now + timedelta(seconds=1),
                correlation_id=command.correlation_id,
                prior_approval_state=EngineeringApprovalState.AWAITING_APPROVAL,
                new_approval_state=EngineeringApprovalState.AWAITING_APPROVAL,
                prior_execution_state=EngineeringExecutionState.EXECUTION_NOT_CONNECTED,
                new_execution_state=EngineeringExecutionState.EXECUTION_NOT_CONNECTED,
                metadata={"instruction_digest": command.instruction_digest},
            ),
        )
    async with fixture.factory() as session:
        events = await EngineeringCommandRepository.list_events(
            session, company_id=fixture.company_id, command_id=command.id
        )
    assert [event.id for event in events] == [first.id, second.id]
    assert events[1].metadata == {"instruction_digest": command.instruction_digest}

    mismatch = AppendEngineeringCommandEvent(
        company_id=fixture.company_id,
        command_id=command.id,
        ecid=command.ecid,
        instruction_digest=command.instruction_digest,
        event_type="mismatch",
        occurred_at=now,
        correlation_id=command.correlation_id,
    )
    cross_company = AppendEngineeringCommandEvent(
        **{
            **mismatch.__dict__,
            "company_id": fixture.other_company_id,
        }
    )
    async with fixture.factory() as session:
        with pytest.raises(ValueError):
            async with session.begin():
                await EngineeringCommandRepository.append_event(
                    session, event=cross_company
                )

    digest_mismatch = AppendEngineeringCommandEvent(
        **{
            **mismatch.__dict__,
            "instruction_digest": "b" * 32,
        }
    )
    async with fixture.factory() as session:
        with pytest.raises(ValueError):
            async with session.begin():
                await EngineeringCommandRepository.append_event(
                    session, event=digest_mismatch
                )


@pytest.mark.asyncio
async def test_event_sequences_are_command_local_and_concurrency_safe(
    engineering_database: EngineeringFixture,
) -> None:
    fixture = engineering_database
    now = datetime.now(timezone.utc)
    async with fixture.factory() as session, session.begin():
        first_command = await EngineeringCommandRepository.create_command(
            session, command=command_input(fixture, created_at=now)
        )
        second_command = await EngineeringCommandRepository.create_command(
            session,
            command=command_input(fixture, created_at=now + timedelta(microseconds=1)),
        )

    async def append(index: int) -> int:
        async with fixture.factory() as session, session.begin():
            event = await EngineeringCommandRepository.append_event(
                session,
                event=AppendEngineeringCommandEvent(
                    company_id=fixture.company_id,
                    command_id=first_command.id,
                    ecid=first_command.ecid,
                    instruction_digest=first_command.instruction_digest,
                    event_type=f"engineering.concurrent_{index}",
                    occurred_at=now + timedelta(seconds=index),
                    correlation_id=first_command.correlation_id,
                ),
            )
            return event.sequence_number

    sequences = await asyncio.gather(*(append(index) for index in range(1, 7)))
    assert sorted(sequences) == [1, 2, 3, 4, 5, 6]

    async with fixture.factory() as session, session.begin():
        independent = await EngineeringCommandRepository.append_event(
            session,
            event=AppendEngineeringCommandEvent(
                company_id=fixture.company_id,
                command_id=second_command.id,
                ecid=second_command.ecid,
                instruction_digest=second_command.instruction_digest,
                event_type="engineering.command_created",
                occurred_at=now,
                correlation_id=second_command.correlation_id,
            ),
        )
    assert independent.sequence_number == 1
    async with fixture.factory() as session:
        listed = await EngineeringCommandRepository.list_events(
            session,
            company_id=fixture.company_id,
            command_id=first_command.id,
        )
    assert [event.sequence_number for event in listed] == [1, 2, 3, 4, 5, 6]


@pytest.mark.asyncio
async def test_command_history_restricts_deletion(
    engineering_database: EngineeringFixture,
) -> None:
    fixture = engineering_database
    now = datetime.now(timezone.utc)
    async with fixture.factory() as session, session.begin():
        command = await EngineeringCommandRepository.create_command(
            session, command=command_input(fixture, created_at=now)
        )
        await EngineeringCommandRepository.append_event(
            session,
            event=AppendEngineeringCommandEvent(
                company_id=fixture.company_id,
                command_id=command.id,
                ecid=command.ecid,
                instruction_digest=command.instruction_digest,
                event_type="engineering.command_created",
                occurred_at=now,
                correlation_id=command.correlation_id,
            ),
        )
    async with fixture.factory() as session:
        with pytest.raises(IntegrityError):
            async with session.begin():
                await session.execute(
                    delete(EngineeringCommand).where(
                        EngineeringCommand.id == command.id
                    )
                )
