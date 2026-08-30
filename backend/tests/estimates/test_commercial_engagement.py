from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.estimates.contracts import EstimateTransitionSpec
from app.estimates.models import (
    CommercialPolicyVersion,
    EstimateFollowUpEvidence,
    EstimatePresentationAuthority,
)
from app.estimates.router import (
    _enforce_discount_policy,
    estimate_commercial_history,
    follow_up_queue,
    prepare_estimate_presentation,
    protected_estimate_decision,
    protected_estimate_view,
    record_follow_up,
)
from app.estimates.schemas import (
    FollowUpWrite,
    PresentationPrepareInput,
    ProtectedEstimateDecision,
)
from app.estimates.service import EstimateService
from app.events.models import BusinessEvent
from sqlalchemy import func, select
from tests.estimates.test_estimate_foundation import make_spec

pytest_plugins = ("tests.estimates.test_estimate_foundation",)


@pytest.mark.asyncio
async def test_discount_policy_fails_closed_and_honors_explicit_limit(
    estimate_fixture,
) -> None:
    factory, company, branch, actor, *_ = estimate_fixture
    async with factory() as session:
        with pytest.raises(Exception, match="unconfigured"):
            await _enforce_discount_policy(session, company_id=company.id, branch_id=branch.id, discount_type="percentage", discount_value=Decimal(5))
        await session.commit()
    async with factory() as session, session.begin():
        session.add(CommercialPolicyVersion(company_id=company.id, branch_id=branch.id, policy_type="discount", status="active", configuration={"mode": "permitted", "maximum_percentage": "10"}, readiness_reason="Synthetic policy", version=1, evidence_digest="a" * 64, idempotency_key=f"discount:{uuid4()}", created_by_user_id=actor.id))
    async with factory() as session:
        await _enforce_discount_policy(session, company_id=company.id, branch_id=branch.id, discount_type="percentage", discount_value=Decimal(10))
        with pytest.raises(Exception, match="exceeds"):
            await _enforce_discount_policy(session, company_id=company.id, branch_id=branch.id, discount_type="percentage", discount_value=Decimal(11))


@pytest.mark.asyncio
async def test_follow_up_is_append_only_idempotent_and_company_scoped(
    estimate_fixture,
) -> None:
    factory, company, branch, actor, customer, location, snapshot = estimate_fixture
    async with factory() as session:
        estimate = await EstimateService().create(
            session,
            spec=make_spec(company, branch, actor, customer, location, snapshot),
        )
    context = SimpleNamespace(company=company, user=actor, authorized_branches=(branch,))
    command = FollowUpWrite(
        branch_id=branch.id,
        assigned_user_id=actor.id,
        state="open",
        due_at=None,
        occurred_at=datetime.now(timezone.utc),
        idempotency_key=f"followup:{uuid4()}",
    )
    async with factory() as session:
        created = await record_follow_up(estimate.id, command, context, session)
    async with factory() as session:
        replay = await record_follow_up(estimate.id, command, context, session)
        queue = await follow_up_queue(context, session, None)
        history = await estimate_commercial_history(estimate.id, context, session)
    assert replay == created
    assert queue == (created,)
    assert any(item.evidence_type == "follow_up" and item.state == "open" for item in history)
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(EstimateFollowUpEvidence)) == 1
        assert await session.scalar(select(func.count()).select_from(BusinessEvent).where(BusinessEvent.event_type == "estimate.follow_up_changed")) == 1


@pytest.mark.asyncio
async def test_protected_presentation_binds_revision_and_records_one_view(
    estimate_fixture,
) -> None:
    factory, company, branch, actor, customer, location, snapshot = estimate_fixture
    service = EstimateService()
    async with factory() as session:
        estimate = await service.create(
            session,
            spec=make_spec(company, branch, actor, customer, location, snapshot),
        )
    now = datetime.now(timezone.utc) + timedelta(seconds=1)
    async with factory() as session:
        estimate = await service.send(
            session,
            spec=EstimateTransitionSpec(
                company_id=company.id,
                branch_id=branch.id,
                estimate_id=estimate.id,
                expected_version=estimate.version,
                actor_user_id=actor.id,
                occurred_at=now,
            ),
        )
    context = SimpleNamespace(company=company, user=actor, authorized_branches=(branch,))
    command = PresentationPrepareInput(
        branch_id=branch.id,
        recipient_reference="customer-reference",
        channel="protected_link",
        expires_at=now + timedelta(days=7),
        idempotency_key=f"presentation:{uuid4()}",
    )
    async with factory() as session:
        credential = await prepare_estimate_presentation(estimate.id, command, context, session)
    assert credential.access_token not in credential.model_dump(exclude={"access_token"}).values()
    async with factory() as session:
        viewed = await protected_estimate_view(session, credential.access_token)
    assert viewed.presentation.status == "viewed"
    assert viewed.artifact.revision_id == estimate.current_revision.id
    async with factory() as session:
        replay = await protected_estimate_view(session, credential.access_token)
        assert replay.presentation.id == credential.id
        assert await session.scalar(select(func.count()).select_from(EstimatePresentationAuthority)) == 1
        assert await session.scalar(select(func.count()).select_from(BusinessEvent).where(BusinessEvent.event_type == "estimate.presentation_viewed")) == 1
    async with factory() as session:
        decided = await protected_estimate_decision(
            ProtectedEstimateDecision(
                revision_id=estimate.current_revision.id,
                decision="approve",
                customer_name="Synthetic Customer",
                occurred_at=now + timedelta(seconds=2),
            ),
            session,
            credential.access_token,
        )
    assert decided.status == "approved"
    async with factory() as session:
        replay = await protected_estimate_decision(
            ProtectedEstimateDecision(
                revision_id=estimate.current_revision.id,
                decision="approve",
                customer_name="Synthetic Customer",
                occurred_at=now + timedelta(seconds=2),
            ),
            session,
            credential.access_token,
        )
    assert replay.id == decided.id
    async with factory() as session:
        with pytest.raises(Exception, match="conflicts"):
            await protected_estimate_decision(
                ProtectedEstimateDecision(
                    revision_id=estimate.current_revision.id,
                    decision="reject",
                    customer_name="Synthetic Customer",
                    rejection_reason="Changed decision",
                    occurred_at=now + timedelta(seconds=3),
                ),
                session,
                credential.access_token,
            )
