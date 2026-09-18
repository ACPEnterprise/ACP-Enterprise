"""PostgreSQL evidence for Payroll cutover replay and contradiction safety."""

import asyncio
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from app.core.config import settings
from app.database.session import get_database_session
from app.events.models import BusinessEvent
from app.main import app as enterprise_app
from app.payroll.cutover_router import router as cutover_router
from app.payroll.models import PayrollCutoverReviewRecord
from app.payroll.permissions import PayrollPermission
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.idempotency.contracts import (
    IdempotencyIdentity,
    canonical_request_digest,
)
from app.platform.idempotency.models import MutationReceipt
from app.platform.idempotency.reliability import (
    AuthoritativeOutcome,
    IdempotencyConflict,
    MutationDisposition,
    RetentionClass,
    mutation_reliability_service,
)
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.dependencies import get_authorization_context
from app.platform.permissions.models import Permission
from app.platform.users.models import User
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

OPERATIONS = (
    "payroll.cutover_review.create",
    "payroll.cutover_review.save_fact",
    "payroll.cutover_review.certify_fact",
    "payroll.cutover_review.create_bridge_period",
    "payroll.cutover_review.write_bridge_fact",
    "payroll.cutover_review.certify_bridge_period",
    "payroll.cutover_review.approve",
)


@pytest_asyncio.fixture
async def replay_database() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _authority(
    factory: async_sessionmaker[AsyncSession], operation: str
) -> tuple[UUID, UUID, UUID]:
    suffix = uuid4().hex[:10]
    async with factory() as session, session.begin():
        user = User(
            normalized_email=f"cutover-replay-{suffix}@example.invalid",
            first_name="Cutover",
            last_name="Replay",
            display_name="Cutover Replay",
            status="active",
        )
        company = Company(
            name=f"Cutover Replay {suffix}",
            code=f"CR{suffix}".upper(),
            status="active",
            timezone="America/New_York",
        )
        session.add_all([user, company])
        await session.flush()
        review = PayrollCutoverReviewRecord(
            company_id=company.id,
            version=1,
            lifecycle="draft",
            created_by_user_id=user.id,
        )
        session.add(review)
        await session.flush()
        return company.id, user.id, review.id


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", OPERATIONS)
async def test_each_cutover_operation_exactly_replays_and_rejects_contradiction(
    replay_database: async_sessionmaker[AsyncSession], operation: str
) -> None:
    company_id, actor_id, review_id = await _authority(replay_database, operation)
    mutations = 0

    async def execute(payload: dict[str, object]):
        async with replay_database() as session:

            async def mutate() -> AuthoritativeOutcome[PayrollCutoverReviewRecord]:
                nonlocal mutations
                mutations += 1
                value = await session.get(PayrollCutoverReviewRecord, review_id)
                assert value is not None
                return AuthoritativeOutcome(
                    value, "payroll_cutover_review", value.id, 200
                )

            async def recover(result_id: UUID) -> PayrollCutoverReviewRecord | None:
                return await session.scalar(
                    select(PayrollCutoverReviewRecord).where(
                        PayrollCutoverReviewRecord.company_id == company_id,
                        PayrollCutoverReviewRecord.id == result_id,
                    )
                )

            return await mutation_reliability_service.execute(
                session,
                identity=IdempotencyIdentity(
                    company_id=company_id,
                    operation=operation,
                    idempotency_key="stable-cutover-command",
                ),
                actor_user_id=actor_id,
                request_digest=canonical_request_digest(payload),
                retention_class=RetentionClass.FINANCIAL_AUDIT,
                mutate=mutate,
                recover=recover,
            )

    first = await execute({"semantic": "original", "protected_value": "secret-a"})
    replay = await execute({"protected_value": "secret-a", "semantic": "original"})
    assert first.disposition is MutationDisposition.EXECUTED
    assert replay.disposition is MutationDisposition.REPLAYED
    assert first.receipt_id == replay.receipt_id
    assert first.value.id == replay.value.id == review_id
    assert mutations == 1

    with pytest.raises(IdempotencyConflict):
        await execute({"semantic": "changed", "protected_value": "secret-b"})

    async with replay_database() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(MutationReceipt)
                .where(
                    MutationReceipt.company_id == company_id,
                    MutationReceipt.operation == operation,
                )
            )
            == 1
        )
        receipt = await session.scalar(
            select(MutationReceipt).where(
                MutationReceipt.company_id == company_id,
                MutationReceipt.operation == operation,
            )
        )
        assert receipt is not None
        assert "secret-a" not in receipt.request_digest
        assert "secret-b" not in receipt.request_digest


@pytest.mark.asyncio
async def test_concurrent_duplicate_cutover_command_has_one_authority_transition(
    replay_database: async_sessionmaker[AsyncSession],
) -> None:
    operation = OPERATIONS[-1]
    company_id, actor_id, review_id = await _authority(replay_database, operation)
    mutations = 0

    async def execute(value: str):
        async with replay_database() as session:

            async def mutate() -> AuthoritativeOutcome[PayrollCutoverReviewRecord]:
                nonlocal mutations
                mutations += 1
                await asyncio.sleep(0.05)
                review = await session.get(PayrollCutoverReviewRecord, review_id)
                assert review is not None
                return AuthoritativeOutcome(
                    review, "payroll_cutover_review", review.id, 200
                )

            async def recover(result_id: UUID) -> PayrollCutoverReviewRecord | None:
                return await session.get(PayrollCutoverReviewRecord, result_id)

            return await mutation_reliability_service.execute(
                session,
                identity=IdempotencyIdentity(
                    company_id=company_id,
                    operation=operation,
                    idempotency_key="concurrent-cutover-command",
                ),
                actor_user_id=actor_id,
                request_digest=canonical_request_digest({"value": value}),
                retention_class=RetentionClass.FINANCIAL_AUDIT,
                mutate=mutate,
                recover=recover,
            )

    first, second = await asyncio.gather(execute("same"), execute("same"))
    assert {first.disposition, second.disposition} == {
        MutationDisposition.EXECUTED,
        MutationDisposition.REPLAYED,
    }
    assert first.receipt_id == second.receipt_id
    assert mutations == 1


@pytest.mark.asyncio
async def test_concurrent_conflicting_cutover_command_fails_deterministically(
    replay_database: async_sessionmaker[AsyncSession],
) -> None:
    operation = OPERATIONS[2]
    company_id, actor_id, review_id = await _authority(replay_database, operation)
    mutations = 0

    async def execute(value: str):
        async with replay_database() as session:

            async def mutate() -> AuthoritativeOutcome[PayrollCutoverReviewRecord]:
                nonlocal mutations
                mutations += 1
                await asyncio.sleep(0.05)
                review = await session.get(PayrollCutoverReviewRecord, review_id)
                assert review is not None
                return AuthoritativeOutcome(
                    review, "payroll_cutover_review", review.id, 200
                )

            async def recover(result_id: UUID) -> PayrollCutoverReviewRecord | None:
                return await session.get(PayrollCutoverReviewRecord, result_id)

            return await mutation_reliability_service.execute(
                session,
                identity=IdempotencyIdentity(
                    company_id=company_id,
                    operation=operation,
                    idempotency_key="concurrent-conflicting-command",
                ),
                actor_user_id=actor_id,
                request_digest=canonical_request_digest({"value": value}),
                retention_class=RetentionClass.FINANCIAL_AUDIT,
                mutate=mutate,
                recover=recover,
            )

    results = await asyncio.gather(
        execute("first"), execute("conflict"), return_exceptions=True
    )
    assert sum(isinstance(result, IdempotencyConflict) for result in results) == 1
    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert mutations == 1


def test_all_cutover_requests_expose_command_identity_and_versions() -> None:
    schema = enterprise_app.openapi()
    paths = schema["paths"]
    for path in (
        "/api/v1/payroll/cutover-review",
        "/api/v1/payroll/cutover-review/facts",
        "/api/v1/payroll/cutover-review/certifications",
        "/api/v1/payroll/cutover-review/bridge-periods",
        "/api/v1/payroll/cutover-review/bridge-periods/{bridge_period_id}/facts",
        "/api/v1/payroll/cutover-review/bridge-periods/{bridge_period_id}/certify",
        "/api/v1/payroll/cutover-review/approve",
    ):
        request = paths[path]["post"]["requestBody"]["content"]["application/json"]
        reference = request["schema"]["$ref"].rsplit("/", 1)[-1]
        properties = schema["components"]["schemas"][reference]["properties"]
        assert "idempotency_key" in properties

    assert (
        "expected_version"
        in schema["components"]["schemas"]["BridgeCertification"]["properties"]
    )
    assert (
        "expected_review_version"
        in schema["components"]["schemas"]["CutoverApproval"]["properties"]
    )
    assert (
        "expected_period_version"
        in schema["components"]["schemas"]["BridgeFactWrite"]["properties"]
    )


@pytest.mark.asyncio
async def test_create_review_http_replay_has_one_event_and_contradiction_is_409(
    replay_database: async_sessionmaker[AsyncSession],
) -> None:
    suffix = uuid4().hex[:10]
    async with replay_database() as session, session.begin():
        user = User(
            normalized_email=f"cutover-http-{suffix}@example.invalid",
            first_name="Cutover",
            last_name="Owner",
            display_name="Cutover Owner",
            status="active",
        )
        company = Company(
            name=f"Cutover HTTP {suffix}",
            code=f"CH{suffix}".upper(),
            status="active",
            timezone="America/New_York",
        )
        session.add_all([user, company])
        await session.flush()
        membership = Membership(
            user_id=user.id,
            company_id=company.id,
            status="active",
            has_all_branch_access=False,
        )
        permission = await session.scalar(
            select(Permission).where(
                Permission.code == PayrollPermission.CUTOVER_OWNER_CERTIFY
            )
        )
        assert permission is not None
        session.add(membership)

    context = AuthorizationContext(
        user=user,
        company=company,
        membership=membership,
        authorized_branches=(),
        active_branch=None,
        effective_roles=(),
        effective_permissions=(permission,),
        credential_version=1,
        authorization_version=1,
    )
    app = FastAPI()
    app.include_router(cutover_router)

    async def database_override() -> AsyncIterator[AsyncSession]:
        async with replay_database() as session:
            yield session

    async def context_override() -> AuthorizationContext:
        return context

    app.dependency_overrides[get_database_session] = database_override
    app.dependency_overrides[get_authorization_context] = context_override
    payload = {
        "proposed_legacy_period_end": "2026-09-11",
        "proposed_acp_period_start": "2026-09-12",
        "opening_ytd_effective_date": "2026-09-12",
        "idempotency_key": "cutover-review-http-replay",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.post("/api/v1/payroll/cutover-review", json=payload)
        replay = await client.post("/api/v1/payroll/cutover-review", json=payload)
        contradiction = await client.post(
            "/api/v1/payroll/cutover-review",
            json={**payload, "proposed_acp_period_start": "2026-09-19"},
        )

    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert contradiction.status_code == 409
    assert contradiction.json()["detail"]["code"] == "idempotency_conflict"
    async with replay_database() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(PayrollCutoverReviewRecord)
                .where(PayrollCutoverReviewRecord.company_id == company.id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(BusinessEvent)
                .where(
                    BusinessEvent.company_id == company.id,
                    BusinessEvent.entity_type == "payroll_cutover_review",
                )
            )
            == 1
        )
