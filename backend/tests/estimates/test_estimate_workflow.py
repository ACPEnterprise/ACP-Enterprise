from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from app.estimates.artifact import render_estimate_artifact
from app.estimates.contracts import (
    CreateEstimateRevisionSpec,
    EstimateDecisionSpec,
    EstimateTransitionSpec,
)
from app.estimates.errors import (
    EstimateConflictError,
    EstimateNotFoundError,
    EstimateValidationError,
)
from app.estimates.models import EstimateCustomerDecision, EstimateLifecycleHistory
from app.estimates.repository import EstimateRepository
from app.estimates.schemas import EstimateItem
from app.estimates.service import EstimateService
from app.events.models import BusinessEvent
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError
from tests.estimates.test_estimate_foundation import make_spec

pytest_plugins = ("tests.estimates.test_estimate_foundation",)


def transition(record, branch, actor, *, occurred_at=None) -> EstimateTransitionSpec:
    return EstimateTransitionSpec(
        company_id=record.company_id,
        branch_id=branch.id,
        estimate_id=record.id,
        expected_version=record.version,
        actor_user_id=actor.id,
        occurred_at=occurred_at or datetime.now(timezone.utc),
    )


def decision(
    base: EstimateTransitionSpec,
    *,
    customer_name: str,
    customer_email: str | None = None,
    customer_comment: str | None = None,
    rejection_reason: str | None = None,
    evidence_reference: str | None = None,
) -> EstimateDecisionSpec:
    return EstimateDecisionSpec(
        company_id=base.company_id,
        branch_id=base.branch_id,
        estimate_id=base.estimate_id,
        expected_version=base.expected_version,
        actor_user_id=base.actor_user_id,
        occurred_at=base.occurred_at,
        customer_name=customer_name,
        customer_email=customer_email,
        customer_comment=customer_comment,
        rejection_reason=rejection_reason,
        evidence_reference=evidence_reference,
    )


@pytest.mark.asyncio
async def test_estimate_artifact_is_deterministic_snapshot_bound_and_safe(
    estimate_fixture,
) -> None:
    factory, company, branch, actor, customer, location, snapshot = estimate_fixture
    service = EstimateService()
    spec = make_spec(company, branch, actor, customer, location, snapshot)
    spec = replace(spec, proposal_title="Safe <proposal>")
    async with factory() as session:
        record = await service.create(session, spec=spec)
    first = render_estimate_artifact(EstimateItem.model_validate(record))
    replay = render_estimate_artifact(EstimateItem.model_validate(record))
    assert first == replay
    assert len(first.artifact_digest) == 64
    assert str(snapshot.id) not in first.content
    assert "Safe &lt;proposal&gt;" in first.content
    assert "DRAFT PREVIEW" in first.content
    assert first.revision_id == record.current_revision.id
    assert first.filename == f"{record.estimate_number}-r1.html"


@pytest.mark.asyncio
async def test_revision_lineage_is_deterministic_and_historical_revision_survives(
    estimate_fixture,
) -> None:
    factory, company, branch, actor, customer, location, snapshot = estimate_fixture
    service = EstimateService()
    async with factory() as session:
        created = await service.create(
            session,
            spec=make_spec(company, branch, actor, customer, location, snapshot),
        )
    revision_spec = CreateEstimateRevisionSpec(
        company_id=company.id,
        branch_id=branch.id,
        estimate_id=created.id,
        expected_version=created.version,
        actor_user_id=actor.id,
        proposal_title="Revised proposal",
        customer_message="Updated scope",
        terms="Valid for 30 days",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        lines=make_spec(company, branch, actor, customer, location, snapshot).lines,
    )
    async with factory() as session:
        revised = await service.revise(session, spec=revision_spec)
    assert revised.current_revision.revision_number == 2
    assert revised.current_revision.parent_revision_id == created.current_revision.id
    assert revised.current_revision.lines[0].snapshot_id == snapshot.id
    assert revised.current_revision.lines[0].snapshot_digest == "a" * 64
    async with factory() as session:
        revisions = await EstimateRepository.list_revisions(
            session, company_id=company.id, estimate_id=created.id
        )
    assert [(item.revision_number, item.proposal_title) for item in revisions] == [
        (1, "Foundation proposal"),
        (2, "Revised proposal"),
    ]


@pytest.mark.asyncio
async def test_sent_viewed_approved_workflow_records_events_and_customer_evidence(
    estimate_fixture,
) -> None:
    factory, company, branch, actor, customer, location, snapshot = estimate_fixture
    service = EstimateService()
    async with factory() as session:
        record = await service.create(
            session,
            spec=make_spec(company, branch, actor, customer, location, snapshot),
        )
    async with factory() as session:
        record = await service.send(session, spec=transition(record, branch, actor))
    assert (record.status, record.acceptance_status) == ("sent", "pending")
    async with factory() as session:
        record = await service.mark_viewed(
            session, spec=transition(record, branch, actor)
        )
    assert record.status == "viewed"
    approval = decision(
        transition(record, branch, actor),
        customer_name="Pat Customer",
        customer_email="pat@example.test",
        customer_comment="Approved as proposed",
        evidence_reference="customer-portal-request-1",
    )
    async with factory() as session:
        record = await service.approve(session, spec=approval)
    assert (record.status, record.acceptance_status) == ("approved", "approved")
    assert record.customer_decision is not None
    assert record.customer_decision.customer_name == "Pat Customer"
    assert record.customer_decision.revision_id == record.current_revision.id
    async with factory() as session:
        event_types = tuple(
            await session.scalars(
                select(BusinessEvent.event_type)
                .where(BusinessEvent.entity_id == record.id)
                .order_by(BusinessEvent.occurred_at, BusinessEvent.id)
            )
        )
    assert "estimate.sent" in event_types
    assert "estimate.viewed" in event_types
    assert "estimate.approved" in event_types
    async with factory() as session:
        lifecycle = tuple(
            await session.scalars(
                select(EstimateLifecycleHistory.to_status)
                .where(EstimateLifecycleHistory.estimate_id == record.id)
                .order_by(EstimateLifecycleHistory.version)
            )
        )
    assert lifecycle == ("draft", "sent", "viewed", "approved")


@pytest.mark.asyncio
async def test_rejection_requires_and_preserves_reason(estimate_fixture) -> None:
    factory, company, branch, actor, customer, location, snapshot = estimate_fixture
    service = EstimateService()
    async with factory() as session:
        record = await service.create(
            session,
            spec=make_spec(company, branch, actor, customer, location, snapshot),
        )
    async with factory() as session:
        record = await service.send(session, spec=transition(record, branch, actor))
    base = transition(record, branch, actor)
    with pytest.raises(EstimateValidationError, match="requires a reason"):
        async with factory() as session:
            await service.reject(
                session,
                spec=decision(base, customer_name="Pat Customer"),
            )
    async with factory() as session:
        rejected = await service.reject(
            session,
            spec=decision(
                base,
                customer_name="Pat Customer",
                rejection_reason="Scope needs revision",
            ),
        )
    assert rejected.status == "rejected"
    assert rejected.customer_decision is not None
    assert rejected.customer_decision.rejection_reason == "Scope needs revision"
    async with factory() as session:
        assert await session.scalar(
            select(BusinessEvent.id).where(
                BusinessEvent.entity_id == rejected.id,
                BusinessEvent.event_type == "estimate.rejected",
            )
        )


@pytest.mark.asyncio
async def test_customer_decision_is_database_immutable(estimate_fixture) -> None:
    factory, company, branch, actor, customer, location, snapshot = estimate_fixture
    service = EstimateService()
    async with factory() as session:
        record = await service.create(
            session,
            spec=make_spec(company, branch, actor, customer, location, snapshot),
        )
    async with factory() as session:
        record = await service.send(session, spec=transition(record, branch, actor))
    decision_spec = decision(
        transition(record, branch, actor), customer_name="Pat Customer"
    )
    async with factory() as session:
        approved = await service.approve(session, spec=decision_spec)
    assert approved.customer_decision is not None
    async with factory() as session:
        with pytest.raises(DBAPIError, match="immutable"):
            await session.execute(
                update(EstimateCustomerDecision)
                .where(EstimateCustomerDecision.id == approved.customer_decision.id)
                .values(customer_name="Changed")
            )
        await session.rollback()


@pytest.mark.asyncio
async def test_expiry_requires_effective_expiry_and_emits_event(
    estimate_fixture,
) -> None:
    factory, company, branch, actor, customer, location, snapshot = estimate_fixture
    service = EstimateService()
    async with factory() as session:
        record = await service.create(
            session,
            spec=make_spec(company, branch, actor, customer, location, snapshot),
        )
    async with factory() as session:
        record = await service.send(session, spec=transition(record, branch, actor))
    assert record.current_revision.expires_at is not None
    after_expiry = record.current_revision.expires_at + timedelta(seconds=1)
    async with factory() as session:
        expired = await service.expire(
            session,
            spec=transition(record, branch, actor, occurred_at=after_expiry),
        )
    assert (expired.status, expired.acceptance_status) == ("expired", "expired")
    async with factory() as session:
        assert await session.scalar(
            select(BusinessEvent.id).where(
                BusinessEvent.entity_id == expired.id,
                BusinessEvent.event_type == "estimate.expired",
            )
        )


@pytest.mark.asyncio
async def test_premature_expiry_fails_closed(estimate_fixture) -> None:
    factory, company, branch, actor, customer, location, snapshot = estimate_fixture
    service = EstimateService()
    async with factory() as session:
        record = await service.create(
            session,
            spec=make_spec(company, branch, actor, customer, location, snapshot),
        )
    async with factory() as session:
        record = await service.send(session, spec=transition(record, branch, actor))
    with pytest.raises(EstimateValidationError, match="before its expiry"):
        async with factory() as session:
            await service.expire(session, spec=transition(record, branch, actor))


@pytest.mark.asyncio
async def test_invalid_transition_fails_closed(
    estimate_fixture,
) -> None:
    factory, company, branch, actor, customer, location, snapshot = estimate_fixture
    service = EstimateService()
    async with factory() as session:
        record = await service.create(
            session,
            spec=make_spec(company, branch, actor, customer, location, snapshot),
        )
    with pytest.raises(EstimateValidationError, match="draft to viewed"):
        async with factory() as session:
            await service.mark_viewed(session, spec=transition(record, branch, actor))


@pytest.mark.asyncio
async def test_branch_scope_fails_closed(estimate_fixture) -> None:
    factory, company, branch, actor, customer, location, snapshot = estimate_fixture
    service = EstimateService()
    async with factory() as session:
        record = await service.create(
            session,
            spec=make_spec(company, branch, actor, customer, location, snapshot),
        )
    wrong_branch = replace(transition(record, branch, actor), branch_id=uuid4())
    with pytest.raises(EstimateNotFoundError):
        async with factory() as session:
            await service.send(session, spec=wrong_branch)


@pytest.mark.asyncio
async def test_stale_version_fails_closed(estimate_fixture) -> None:
    factory, company, branch, actor, customer, location, snapshot = estimate_fixture
    service = EstimateService()
    async with factory() as session:
        record = await service.create(
            session,
            spec=make_spec(company, branch, actor, customer, location, snapshot),
        )
    stale = replace(transition(record, branch, actor), expected_version=999)
    with pytest.raises(EstimateConflictError, match="stale"):
        async with factory() as session:
            await service.send(session, spec=stale)
