from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.platform.branch.models import Branch
from app.platform.company.models import Company
from app.platform.idempotency.contracts import IdempotencyIdentity
from app.platform.idempotency.models import MutationReceipt
from app.platform.idempotency.reliability import (
    AuthoritativeOutcome,
    IdempotencyConflict,
    MutationDisposition,
    MutationReliabilityService,
    RetentionClass,
)
from app.platform.users.models import User


@pytest_asyncio.fixture
async def mutation_reliability_fixture():
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        company = Company(
            name="Mutation receipt authority",
            code=f"MRA{uuid4().hex[:7].upper()}",
            status="active",
            timezone="America/New_York",
        )
        branch_a = Branch(
            company=company,
            name="Mutation A",
            code=f"A{uuid4().hex[:7].upper()}",
            status="active",
            timezone="America/New_York",
            is_primary=True,
        )
        branch_b = Branch(
            company=company,
            name="Mutation B",
            code=f"B{uuid4().hex[:7].upper()}",
            status="active",
            timezone="America/New_York",
            is_primary=False,
        )
        actor = User(
            normalized_email=f"mutation-{uuid4().hex}@example.test",
            first_name="Mutation",
            last_name="Operator",
            display_name="Mutation Operator",
            status="active",
        )
        session.add_all([company, branch_a, branch_b, actor])
        await session.flush()
    try:
        yield factory, company, branch_a, branch_b, actor
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_exact_replay_requires_immutable_branch_authority(
    mutation_reliability_fixture,
) -> None:
    factory, company, branch_a, branch_b, actor = mutation_reliability_fixture
    service = MutationReliabilityService()
    result_id = uuid4()
    mutation_calls = 0
    recovery_calls = 0

    async def mutate():
        nonlocal mutation_calls
        mutation_calls += 1
        return AuthoritativeOutcome("created", "synthetic", result_id, 201)

    async def recover(identity):
        nonlocal recovery_calls
        recovery_calls += 1
        return "replayed" if identity == result_id else None

    identity = IdempotencyIdentity(
        company.id, "synthetic.branch-bound", f"mutation-{uuid4()}", branch_a.id
    )
    async with factory() as session:
        executed = await service.execute(
            session,
            identity=identity,
            actor_user_id=actor.id,
            request_digest="a" * 64,
            retention_class=RetentionClass.OPERATIONAL,
            mutate=mutate,
            recover=recover,
        )
    assert executed.disposition is MutationDisposition.EXECUTED

    async with factory() as session:
        replayed = await service.execute(
            session,
            identity=identity,
            actor_user_id=actor.id,
            request_digest="a" * 64,
            retention_class=RetentionClass.OPERATIONAL,
            mutate=mutate,
            recover=recover,
        )
    assert replayed.disposition is MutationDisposition.REPLAYED
    assert replayed.value == "replayed"

    foreign_branch_identity = IdempotencyIdentity(
        company.id,
        identity.operation,
        identity.idempotency_key,
        branch_b.id,
    )
    async with factory() as session:
        with pytest.raises(IdempotencyConflict, match="Branch authority"):
            await service.execute(
                session,
                identity=foreign_branch_identity,
                actor_user_id=actor.id,
                request_digest="a" * 64,
                retention_class=RetentionClass.OPERATIONAL,
                mutate=mutate,
                recover=recover,
            )
    assert mutation_calls == 1
    assert recovery_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_fields",
    [
        {"company_id": uuid4()},
        {"branch_id": uuid4()},
        {"actor_user_id": uuid4()},
        {"request_digest": "short"},
        {"response_status": 999},
        {"state": "completed"},
    ],
)
async def test_mutation_receipt_storage_fails_closed(
    mutation_reliability_fixture, invalid_fields
) -> None:
    factory, company, branch, _, actor = mutation_reliability_fixture
    values = {
        "company_id": company.id,
        "branch_id": branch.id,
        "actor_user_id": actor.id,
        "operation": f"synthetic-{uuid4()}",
        "idempotency_key": f"key-{uuid4()}",
        "request_digest": "b" * 64,
        "state": "in_progress",
        "response_status": None,
        "retention_class": "operational",
        **invalid_fields,
    }
    async with factory() as session:
        session.add(MutationReceipt(**values))
        with pytest.raises(IntegrityError):
            await session.commit()
