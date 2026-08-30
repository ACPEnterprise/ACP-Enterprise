from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.estimates.models import CommercialPolicyVersion
from app.estimates.router import commercial_policies, configure_commercial_policy
from app.estimates.schemas import CommercialPolicyWrite
from app.events.models import BusinessEvent
from fastapi import HTTPException
from sqlalchemy import func, select

pytest_plugins = ("tests.estimates.test_estimate_foundation",)


@pytest.mark.asyncio
async def test_commercial_policy_is_versioned_idempotent_and_fail_closed(
    estimate_fixture,
) -> None:
    factory, company, branch, actor, *_ = estimate_fixture
    context = SimpleNamespace(
        company=company, user=actor, authorized_branches=(branch,)
    )
    command = CommercialPolicyWrite(
        branch_id=branch.id,
        policy_type="discount",
        status="unconfigured",
        configuration={},
        readiness_reason="Owner policy value remains unconfigured.",
        idempotency_key=f"commercial-policy-{uuid4()}",
    )
    async with factory() as session:
        created = await configure_commercial_policy(command, context, session)
    assert created.version == 1
    assert created.status == "unconfigured"
    async with factory() as session:
        replay = await configure_commercial_policy(command, context, session)
        listing = await commercial_policies(context, session)
    assert replay.id == created.id
    assert listing == (created,)
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CommercialPolicyVersion)
                .where(CommercialPolicyVersion.company_id == company.id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(BusinessEvent)
                .where(
                    BusinessEvent.company_id == company.id,
                    BusinessEvent.event_type == "commercial.policy.configured",
                )
            )
            == 1
        )
    async with factory() as session:
        with pytest.raises(HTTPException) as conflict:
            await configure_commercial_policy(
                command.model_copy(update={"readiness_reason": "Contradiction"}),
                context,
                session,
            )
    assert conflict.value.status_code == 409


@pytest.mark.asyncio
async def test_active_commercial_policy_requires_explicit_configuration(
    estimate_fixture,
) -> None:
    factory, company, branch, actor, *_ = estimate_fixture
    context = SimpleNamespace(
        company=company, user=actor, authorized_branches=(branch,)
    )
    async with factory() as session:
        with pytest.raises(HTTPException) as invalid:
            await configure_commercial_policy(
                CommercialPolicyWrite(
                    branch_id=branch.id,
                    policy_type="rounding",
                    status="active",
                    configuration={},
                    readiness_reason="Missing explicit mode",
                    idempotency_key=f"commercial-policy-{uuid4()}",
                ),
                context,
                session,
            )
    assert invalid.value.status_code == 422
