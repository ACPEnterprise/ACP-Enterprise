from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.database.session import get_database_session
from app.engineering_control.repository_authorization.contracts import (
    RepositoryAuthorizationState,
    RepositoryOperationType,
)
from app.engineering_control.repository_authorization.errors import (
    RepositoryAuthorizationConflictError,
    RepositoryAuthorizationEvidenceMismatchError,
    RepositoryAuthorizationIneligibleError,
    RepositoryAuthorizationNotFoundError,
)
from app.engineering_control.repository_authorization.models import (
    EngineeringRepositoryAuthorization,
    EngineeringRepositoryAuthorizationEvent,
)
from app.engineering_control.repository_authorization.records import (
    RequestRepositoryAuthorization,
    RevokeRepositoryAuthorization,
    ValidateRepositoryAuthorization,
)
from app.engineering_control.repository_authorization.router import router
from app.engineering_control.repository_authorization.service import (
    EngineeringRepositoryAuthorizationService,
)
from app.engineering_control.review.contracts import EngineeringReviewDecision
from app.engineering_control.review.records import DecideEngineeringReview
from app.engineering_control.review.service import EngineeringReviewService
from app.engineering_execution.composition.contracts import (
    ProviderAttemptState,
    ProviderResultStatus,
)
from app.engineering_execution.composition.service import (
    RecordProviderResult,
)
from app.engineering_execution.status.service import MobileExecutionStatusService
from app.events.models import BusinessEvent
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import EngineeringCommandPermission
from app.platform.permissions.dependencies import get_authorization_context
from tests.engineering_control.test_engineering_command_service import (
    ServiceFixture,
    context_with_permissions,
    seed_service_fixture,
    utc_now,
)
from tests.engineering_execution.composition.test_composition import (
    composition_scenario,
)
from tests.engineering_execution.status.test_execution_status import read_context
from tests.engineering_execution.test_engineering_execution import execution_context

BOUNDARY = ("backend/app/example.py", "backend/tests/test_example.py")


@pytest_asyncio.fixture
async def authorization_database() -> AsyncIterator[ServiceFixture]:
    engine = create_async_engine(settings.database_url)
    fixture = await seed_service_fixture(
        async_sessionmaker(engine, expire_on_commit=False)
    )
    try:
        yield fixture
    finally:
        await engine.dispose()


def owner_context(fixture: ServiceFixture) -> AuthorizationContext:
    return context_with_permissions(
        fixture.context.user,
        fixture.context.company,
        fixture.context.membership,
        tuple(EngineeringCommandPermission.ALL),
    )


async def accepted_review(
    fixture: ServiceFixture,
    *,
    accept: bool = True,
    expected_branch: str = "customer-management-v1",
    expected_head: str = "a" * 40,
):
    (
        composition_service,
        compose,
        command,
        _,
        _,
        _,
        _,
    ) = await composition_scenario(
        fixture,
        expected_branch=expected_branch,
        expected_head=expected_head,
    )
    async with fixture.factory() as session:
        bundle = await composition_service.compose(
            session,
            context=execution_context(fixture.context),
            command=compose,
        )
    async with fixture.factory() as session:
        attempt = await composition_service.prepare_attempt(
            session,
            context=execution_context(fixture.context),
            composition_id=bundle.composition.id,
            idempotency_key=uuid4(),
        )
    async with fixture.factory() as session:
        starting = await composition_service.transition_attempt(
            session,
            context=execution_context(fixture.context),
            attempt_id=attempt.id,
            expected_version=attempt.version,
            to_state=ProviderAttemptState.STARTING,
        )
    async with fixture.factory() as session:
        await composition_service.transition_attempt(
            session,
            context=execution_context(fixture.context),
            attempt_id=attempt.id,
            expected_version=starting.version,
            to_state=ProviderAttemptState.RUNNING,
        )
    async with fixture.factory() as session:
        await composition_service.record_result(
            session,
            context=execution_context(fixture.context),
            command=RecordProviderResult(
                attempt_id=attempt.id,
                status=ProviderResultStatus.SUCCEEDED,
                evidence_summary={"summary": "Bounded reviewed artifact evidence."},
                validation_summary={
                    "bounded_output": True,
                    "file_boundary": list(BOUNDARY),
                },
                output_references=("artifact://reviewed-boundary",),
            ),
        )
    review_service = EngineeringReviewService()
    context = owner_context(fixture)
    async with fixture.factory() as session:
        review = await review_service.prepare(
            session,
            context=context,
            command_id=command.id,
        )
    if accept:
        async with fixture.factory() as session:
            review = await review_service.decide(
                session,
                context=context,
                command=DecideEngineeringReview(
                    review_id=review.review.id,
                    expected_version=review.review.version,
                    review_digest=review.review.review_digest,
                    decision=EngineeringReviewDecision.ACCEPT,
                ),
            )
    return command, review, context


def request_for(review, *, suffix: str = "one") -> RequestRepositoryAuthorization:
    return RequestRepositoryAuthorization(
        review_id=review.review.id,
        review_digest=review.review.review_digest,
        operation_type=RepositoryOperationType.CREATE_COMMIT,
        file_boundary=BOUNDARY,
        expected_branch=review.expected_branch,
        expected_base_commit=review.expected_head,
        expires_at=utc_now() + timedelta(minutes=20),
        idempotency_key=f"repository-authorization-{suffix}",
    )


def validation_for(record) -> ValidateRepositoryAuthorization:
    return ValidateRepositoryAuthorization(
        authorization_id=record.id,
        capability_id=record.capability_id,
        authorization_digest=record.authorization_digest,
        operation_type=record.operation_type,
        file_boundary=record.file_boundary,
        expected_branch=record.expected_branch,
        expected_base_commit=record.expected_base_commit,
    )


@pytest.mark.asyncio
async def test_authorize_validate_consume_and_reject_replay(
    authorization_database: ServiceFixture,
) -> None:
    fixture = authorization_database
    command, review, context = await accepted_review(fixture)
    service = EngineeringRepositoryAuthorizationService()
    async with fixture.factory() as session:
        record = await service.request(
            session,
            context=context,
            command=request_for(review),
        )
    assert record.state is RepositoryAuthorizationState.AUTHORIZED
    assert record.file_boundary == tuple(sorted(BOUNDARY))

    async with fixture.factory() as session:
        validated = await service.validate(
            session,
            context=context,
            command=validation_for(record),
        )
    assert validated.id == record.id

    async with fixture.factory() as session:
        consumed = await service.consume(
            session,
            context=context,
            command=validation_for(record),
        )
    assert consumed.state is RepositoryAuthorizationState.CONSUMED
    async with fixture.factory() as session:
        with pytest.raises(RepositoryAuthorizationIneligibleError):
            await service.consume(
                session,
                context=context,
                command=validation_for(record),
            )

    async with fixture.factory() as session:
        status = await MobileExecutionStatusService().get(
            session,
            context=read_context(fixture),
            command_id=command.id,
        )
        events = (
            await session.scalars(
                select(BusinessEvent).where(
                    BusinessEvent.entity_id == record.id,
                )
            )
        ).all()
    assert status.authorization_required is True
    assert status.authorization_status == "consumed"
    assert status.authorization_eligible is False
    assert status.authorization_consumed_at is not None
    assert {event.event_type for event in events} == {
        "engineering_control.repository_authorization_requested",
        "engineering_control.repository_authorization_granted",
        "engineering_control.repository_authorization_consumed",
    }
    assert all("file_boundary" not in event.payload for event in events)
    assert all("authorization_digest" not in event.payload for event in events)


@pytest.mark.asyncio
async def test_pending_stale_scope_and_cross_company_fail_closed(
    authorization_database: ServiceFixture,
) -> None:
    fixture = authorization_database
    _, pending, context = await accepted_review(fixture, accept=False)
    service = EngineeringRepositoryAuthorizationService()
    async with fixture.factory() as session:
        with pytest.raises(RepositoryAuthorizationNotFoundError):
            await service.request(
                session,
                context=context,
                command=request_for(pending),
            )
    async with fixture.factory() as session:
        rejected = await EngineeringReviewService().decide(
            session,
            context=context,
            command=DecideEngineeringReview(
                review_id=pending.review.id,
                expected_version=pending.review.version,
                review_digest=pending.review.review_digest,
                decision=EngineeringReviewDecision.REJECT,
                reason_code="owner_rejected",
            ),
        )
    async with fixture.factory() as session:
        with pytest.raises(RepositoryAuthorizationEvidenceMismatchError):
            await service.request(
                session,
                context=context,
                command=request_for(rejected, suffix="rejected"),
            )

    _, review, context = await accepted_review(fixture)
    async with fixture.factory() as session:
        with pytest.raises(RepositoryAuthorizationEvidenceMismatchError):
            await service.request(
                session,
                context=context,
                command=replace(
                    request_for(review, suffix="wrong-branch"),
                    expected_branch="unauthorized-branch",
                ),
            )
    async with fixture.factory() as session:
        record = await service.request(
            session,
            context=context,
            command=request_for(review, suffix="valid"),
        )
    async with fixture.factory() as session:
        with pytest.raises(RepositoryAuthorizationEvidenceMismatchError):
            await service.validate(
                session,
                context=context,
                command=replace(
                    validation_for(record),
                    file_boundary=("backend/app/other.py",),
                ),
            )
    async with fixture.factory() as session:
        with pytest.raises(RepositoryAuthorizationNotFoundError):
            await service.get(
                session,
                context=fixture.other_context,
                authorization_id=record.id,
            )


@pytest.mark.asyncio
async def test_expiration_revocation_and_version_conflict(
    authorization_database: ServiceFixture,
) -> None:
    fixture = authorization_database
    _, review, context = await accepted_review(fixture)
    service = EngineeringRepositoryAuthorizationService()
    now = utc_now()
    async with fixture.factory() as session:
        expiring = await service.request(
            session,
            context=context,
            command=replace(
                request_for(review, suffix="expires"),
                expires_at=now + timedelta(seconds=1),
            ),
            now=now,
        )
    async with fixture.factory() as session:
        with pytest.raises(RepositoryAuthorizationIneligibleError):
            await service.validate(
                session,
                context=context,
                command=validation_for(expiring),
                now=now + timedelta(seconds=2),
            )
    async with fixture.factory() as session:
        expired = await session.get(
            EngineeringRepositoryAuthorization,
            expiring.id,
        )
    assert expired is not None
    assert expired.state == "expired"

    _, second_review, context = await accepted_review(fixture)
    async with fixture.factory() as session:
        record = await service.request(
            session,
            context=context,
            command=request_for(second_review, suffix="revoke"),
        )
    async with fixture.factory() as session:
        with pytest.raises(RepositoryAuthorizationConflictError):
            await service.revoke(
                session,
                context=context,
                command=RevokeRepositoryAuthorization(
                    record.id,
                    record.version + 1,
                    "owner_revoked",
                ),
            )
    async with fixture.factory() as session:
        revoked = await service.revoke(
            session,
            context=context,
            command=RevokeRepositoryAuthorization(
                record.id,
                record.version,
                "owner_revoked",
            ),
        )
    assert revoked.state is RepositoryAuthorizationState.REVOKED


@pytest.mark.asyncio
async def test_bounded_authorization_http_api(
    authorization_database: ServiceFixture,
) -> None:
    fixture = authorization_database
    _, review, context = await accepted_review(fixture)
    request = request_for(review, suffix="http")
    app = FastAPI()
    app.include_router(router)

    async def session_override() -> AsyncIterator[AsyncSession]:
        async with fixture.factory() as session:
            yield session

    active_context = {"value": context}

    async def context_override() -> AuthorizationContext:
        return active_context["value"]

    app.dependency_overrides[get_database_session] = session_override
    app.dependency_overrides[get_authorization_context] = context_override
    payload = {
        **request.__dict__,
        "review_id": str(request.review_id),
        "operation_type": request.operation_type.value,
        "expires_at": request.expires_at.isoformat(),
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        created = await client.post(
            "/api/v1/engineering/repository-authorizations",
            json=payload,
        )
        assert created.status_code == 200
        body = created.json()
        assert body["authorization_eligible"] is True
        listed = await client.get(
            "/api/v1/engineering/repository-authorizations",
            params={"limit": 1},
        )
        assert listed.status_code == 200
        assert listed.json()["items"][0]["id"] == body["id"]
        eligible = await client.post(
            f"/api/v1/engineering/repository-authorizations/{body['id']}/eligibility",
            json={
                "capability_id": body["capability_id"],
                "authorization_digest": body["authorization_digest"],
                "operation_type": body["operation_type"],
                "file_boundary": body["file_boundary"],
                "expected_branch": body["expected_branch"],
                "expected_base_commit": body["expected_base_commit"],
            },
        )
        assert eligible.status_code == 200
        assert eligible.json()["eligible"] is True
        revoked = await client.post(
            f"/api/v1/engineering/repository-authorizations/{body['id']}/revoke",
            json={"expected_version": body["version"], "reason_code": "owner_revoked"},
        )
        assert revoked.status_code == 200
        assert revoked.json()["state"] == "revoked"
        active_context["value"] = read_context(fixture)
        forbidden = await client.post(
            "/api/v1/engineering/repository-authorizations",
            json={**payload, "idempotency_key": "repository-authorization-forbidden"},
        )
        assert forbidden.status_code == 403

    async with fixture.factory() as session:
        assert (
            await session.scalar(
                select(func.count(EngineeringRepositoryAuthorizationEvent.id)).where(
                    EngineeringRepositoryAuthorizationEvent.authorization_id
                    == UUID(body["id"])
                )
            )
            == 3
        )
