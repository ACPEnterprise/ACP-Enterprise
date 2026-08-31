from collections.abc import AsyncIterator
from dataclasses import FrozenInstanceError

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.database.session import get_database_session
from app.engineering_control.models import EngineeringCommand
from app.engineering_control.review.contracts import (
    EngineeringReviewDecision,
    EngineeringReviewState,
)
from app.engineering_control.review.errors import (
    EngineeringReviewDigestMismatchError,
    EngineeringReviewNotFoundError,
)
from app.engineering_control.review.models import (
    EngineeringExecutionReview,
    EngineeringExecutionReviewDecision,
)
from app.engineering_control.review.records import DecideEngineeringReview
from app.engineering_control.review.router import router
from app.engineering_control.review.schemas import EngineeringReviewPackageResponse
from app.engineering_control.review.service import EngineeringReviewService
from app.engineering_execution.status.service import MobileExecutionStatusService
from app.engineering_execution.supervision.execution import (
    ExecuteApprovedComposition,
    SupervisedExecutionService,
)
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import EngineeringCommandPermission
from app.platform.permissions.dependencies import get_authorization_context
from tests.engineering_control.test_engineering_command_service import (
    ServiceFixture,
    context_with_permissions,
    seed_service_fixture,
)
from tests.engineering_execution.status.test_execution_status import read_context
from tests.engineering_execution.supervision.test_supervised_execution import (
    prepared_execution,
)


@pytest_asyncio.fixture
async def review_database() -> AsyncIterator[ServiceFixture]:
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


async def completed_command(fixture: ServiceFixture):
    (
        command,
        _,
        attempt,
        context,
        runtime,
        _,
        provider_session,
    ) = await prepared_execution(fixture)
    async with fixture.factory() as session:
        await SupervisedExecutionService(runtime=runtime).execute(
            session,
            context=context,
            command=ExecuteApprovedComposition(
                provider_session.id,
                attempt.idempotency_key,
            ),
        )
    return command


@pytest.mark.asyncio
async def test_prepare_and_accept_exact_review_package(
    review_database: ServiceFixture,
) -> None:
    fixture = review_database
    command = await completed_command(fixture)
    service = EngineeringReviewService()
    context = owner_context(fixture)
    async with fixture.factory() as session:
        package = await service.prepare(
            session,
            context=context,
            command_id=command.id,
        )
    assert package.review.state is EngineeringReviewState.PENDING
    assert package.repository_mutated is False
    assert package.result_status == "succeeded"
    assert package.evidence_summary["structured_text"]
    assert EngineeringReviewPackageResponse.model_validate(package)
    with pytest.raises(FrozenInstanceError):
        package.review.state = EngineeringReviewState.ACCEPTED  # type: ignore[misc]

    async with fixture.factory() as session:
        replay = await service.prepare(
            session,
            context=context,
            command_id=command.id,
        )
    assert replay.review.id == package.review.id

    async with fixture.factory() as session:
        decided = await service.decide(
            session,
            context=context,
            command=DecideEngineeringReview(
                review_id=package.review.id,
                expected_version=package.review.version,
                review_digest=package.review.review_digest,
                decision=EngineeringReviewDecision.ACCEPT,
            ),
        )
    assert decided.review.state is EngineeringReviewState.ACCEPTED
    assert decided.decision is not None
    assert decided.decision.decision is EngineeringReviewDecision.ACCEPT

    async with fixture.factory() as session:
        command_count = await session.scalar(
            select(func.count(EngineeringCommand.id)).where(
                EngineeringCommand.id == command.id
            )
        )
        decision_count = await session.scalar(
            select(func.count(EngineeringExecutionReviewDecision.id)).where(
                EngineeringExecutionReviewDecision.review_id == package.review.id
            )
        )
        stored_command = await session.get(EngineeringCommand, command.id)
    assert command_count == 1
    assert decision_count == 1
    assert stored_command is not None
    assert stored_command.approval_state == "approved"


@pytest.mark.asyncio
async def test_review_fails_closed_for_stale_evidence_and_other_company(
    review_database: ServiceFixture,
) -> None:
    fixture = review_database
    command = await completed_command(fixture)
    service = EngineeringReviewService()
    context = owner_context(fixture)
    async with fixture.factory() as session:
        package = await service.prepare(
            session,
            context=context,
            command_id=command.id,
        )
    async with fixture.factory() as session:
        with pytest.raises(EngineeringReviewDigestMismatchError):
            await service.decide(
                session,
                context=context,
                command=DecideEngineeringReview(
                    review_id=package.review.id,
                    expected_version=package.review.version,
                    review_digest="0" * 64,
                    decision=EngineeringReviewDecision.ACCEPT,
                ),
            )
    async with fixture.factory() as session:
        with pytest.raises(EngineeringReviewNotFoundError):
            await service.get(
                session,
                context=fixture.other_context,
                review_id=package.review.id,
            )


@pytest.mark.asyncio
async def test_review_storage_rejects_foreign_company_evidence_chain(
    review_database: ServiceFixture,
) -> None:
    fixture = review_database
    command = await completed_command(fixture)
    async with fixture.factory() as session:
        package = await EngineeringReviewService().prepare(
            session,
            context=owner_context(fixture),
            command_id=command.id,
        )
    async with fixture.factory() as session, session.begin():
        valid = await session.get(EngineeringExecutionReview, package.review.id)
        assert valid is not None
        session.add(
            EngineeringExecutionReview(
                company_id=fixture.other_context.company.id,
                command_id=valid.command_id,
                execution_id=valid.execution_id,
                composition_id=valid.composition_id,
                attempt_id=valid.attempt_id,
                result_id=valid.result_id,
                controlled_result_id=valid.controlled_result_id,
                provider_identifier=valid.provider_identifier,
                instruction_digest=valid.instruction_digest,
                request_digest=valid.request_digest,
                composition_digest=valid.composition_digest,
                review_digest=valid.review_digest,
                state="pending",
                version=1,
            )
        )
        with pytest.raises(IntegrityError):
            await session.flush()
@pytest.mark.asyncio
async def test_review_projection_and_bounded_http_api(
    review_database: ServiceFixture,
) -> None:
    fixture = review_database
    command = await completed_command(fixture)
    context = owner_context(fixture)
    app = FastAPI()
    app.include_router(router)

    async def session_override() -> AsyncIterator[AsyncSession]:
        async with fixture.factory() as session:
            yield session

    async def context_override() -> AuthorizationContext:
        return context

    app.dependency_overrides[get_database_session] = session_override
    app.dependency_overrides[get_authorization_context] = context_override
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        prepared = await client.post(
            f"/api/v1/engineering/reviews/commands/{command.id}"
        )
        assert prepared.status_code == 200
        body = prepared.json()
        assert body["repository_mutated"] is False
        assert "credential" not in str(body).lower()
        listed = await client.get("/api/v1/engineering/reviews", params={"limit": 1})
        assert listed.status_code == 200
        assert listed.json()["items"][0]["id"] == body["review"]["id"]
        detail = await client.get(f"/api/v1/engineering/reviews/{body['review']['id']}")
        assert detail.status_code == 200

    async with fixture.factory() as session:
        status = await MobileExecutionStatusService().get(
            session,
            context=read_context(fixture),
            command_id=command.id,
        )
    assert status.review_available is True
    assert status.review_id is not None
    assert status.review_state == "pending"
    assert "owner_review_prepared" in {item.event for item in status.timeline}

    async with fixture.factory() as session:
        assert (
            await session.scalar(
                select(func.count(EngineeringExecutionReview.id)).where(
                    EngineeringExecutionReview.command_id == command.id
                )
            )
            == 1
        )


def test_review_model_binds_exact_evidence_lineage() -> None:
    constraints = {
        constraint.name: tuple(constraint.column_keys)
        for constraint in EngineeringExecutionReview.__table__.foreign_key_constraints
    }
    assert constraints["fk_engineering_reviews_exact_execution"] == (
        "company_id",
        "execution_id",
        "command_id",
    )
    assert constraints["fk_engineering_reviews_exact_composition"] == (
        "company_id",
        "composition_id",
        "execution_id",
        "command_id",
    )
    assert constraints["fk_engineering_reviews_exact_attempt"] == (
        "company_id",
        "attempt_id",
        "composition_id",
    )
    assert constraints["fk_engineering_reviews_exact_result"] == (
        "company_id",
        "result_id",
        "attempt_id",
        "composition_id",
    )
    assert constraints["fk_engineering_reviews_exact_controlled_result"] == (
        "company_id",
        "controlled_result_id",
        "execution_id",
        "command_id",
    )
