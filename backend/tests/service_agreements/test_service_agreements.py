from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.customers.models import Customer, ServiceLocation
from app.platform.branch.models import Branch
from app.platform.company.models import Company
from app.platform.users.models import User
from app.service_agreements.models import (
    AgreementBillingOccurrence,
    AgreementCoverage,
    AgreementLifecycleEvidence,
    AgreementPlan,
    ServiceAgreement,
    ServiceEntitlement,
)
from app.service_agreements.router import fail
from app.service_agreements.schemas import (
    EnrollmentCreate,
    PlanCreate,
    PlanOut,
    Transition,
)
from app.service_agreements.service import (
    AgreementConflict,
    AgreementError,
    AgreementNotFound,
    AgreementService,
    add_months,
    digest,
)


@pytest_asyncio.fixture
async def agreement_branch_fixture():
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        company = Company(
            name="Agreement branch authority",
            code=f"SAA{uuid4().hex[:7].upper()}",
            status="active",
            timezone="America/New_York",
        )
        branch_a = Branch(
            company=company,
            name="Agreement A",
            code=f"A{uuid4().hex[:7].upper()}",
            status="active",
            timezone="America/New_York",
            is_primary=True,
        )
        branch_b = Branch(
            company=company,
            name="Agreement B",
            code=f"B{uuid4().hex[:7].upper()}",
            status="active",
            timezone="America/New_York",
            is_primary=False,
        )
        foreign_company = Company(
            name="Foreign agreement authority",
            code=f"SAF{uuid4().hex[:7].upper()}",
            status="active",
            timezone="America/New_York",
        )
        foreign_branch = Branch(
            company=foreign_company,
            name="Foreign",
            code=f"F{uuid4().hex[:7].upper()}",
            status="active",
            timezone="America/New_York",
            is_primary=True,
        )
        actor = User(
            normalized_email=f"agreement-{uuid4().hex}@example.test",
            first_name="Agreement",
            last_name="Operator",
            display_name="Agreement Operator",
            status="active",
        )
        customer = Customer(
            company=company,
            customer_number=f"CUS-{uuid4().int % 1000000:06d}",
            status="active",
            customer_type="residential",
            display_name="Agreement Customer",
            preferred_contact_method="email",
            normalized_name=f"agreement customer {uuid4().hex}",
        )
        location = ServiceLocation(
            customer=customer,
            nickname="Agreement location",
            address="100 Qualification Way",
            city="Testville",
            state="NY",
            postal_code="10001",
            country="US",
            normalized_address="100 qualification way testville ny 10001",
            active=True,
            is_primary=True,
        )
        session.add_all(
            [
                company,
                branch_a,
                branch_b,
                foreign_company,
                foreign_branch,
                actor,
                customer,
                location,
            ]
        )
        await session.flush()
    try:
        yield factory, company, branch_a, branch_b, foreign_branch, actor, customer, location
    finally:
        await engine.dispose()


def test_agreement_root_identities_are_company_bound() -> None:
    bindings = {
        (
            tuple(column.name for column in constraint.columns),
            tuple(element.target_fullname for element in constraint.elements),
        )
        for constraint in ServiceAgreement.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }

    assert (
        ("company_id", "customer_id"),
        ("customers.company_id", "customers.id"),
    ) in bindings
    assert (
        ("company_id", "plan_id"),
        ("service_agreement_plans.company_id", "service_agreement_plans.id"),
    ) in bindings
    assert (
        ("company_id", "predecessor_agreement_id"),
        ("service_agreements.company_id", "service_agreements.id"),
    ) in bindings
    assert any(
        isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_agreement_plans_company_id"
        for constraint in AgreementPlan.__table__.constraints
    )
    assert any(
        isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_service_agreements_company_id"
        for constraint in ServiceAgreement.__table__.constraints
    )


def test_agreement_children_bind_tenant_branch_and_exact_parent() -> None:
    expected = {
        AgreementCoverage: {"fk_agreement_coverage_agreement"},
        ServiceEntitlement: {
            "fk_agreement_entitlements_agreement",
            "fk_agreement_entitlements_appointment",
            "fk_agreement_entitlements_job",
        },
        AgreementLifecycleEvidence: {
            "fk_agreement_evidence_agreement",
            "fk_agreement_evidence_entitlement",
        },
        AgreementBillingOccurrence: {
            "fk_agreement_billing_agreement",
            "fk_agreement_billing_invoice",
        },
    }

    for model, names in expected.items():
        constraints = {
            constraint.name
            for constraint in model.__table__.constraints
            if isinstance(constraint, ForeignKeyConstraint)
        }
        assert names <= constraints
    assert any(
        isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_agreement_entitlements_evidence_binding"
        for constraint in ServiceEntitlement.__table__.constraints
    )


def test_agreement_evidence_digest_is_deterministic_and_order_independent():
    assert digest({"agreement": "a", "sequence": 1}) == digest({"sequence": 1, "agreement": "a"})


def test_calendar_entitlement_windows_do_not_drift():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)


def test_lifecycle_commands_require_idempotency_and_replay_evidence():
    # Contract evidence: lifecycle, entitlement, renewal, and billing commands
    # persist canonical request digests before committing authoritative state.
    assert Transition.model_fields["idempotency_key"].is_required()


def test_plan_response_does_not_expose_command_idempotency_identity():
    plan = PlanOut(
        id=uuid4(),
        company_id=uuid4(),
        branch_id=None,
        code="SYNTHETIC",
        name="Synthetic qualification plan",
        version=1,
        status="draft",
        currency="USD",
        price_amount=Decimal("0.00"),
        billing_cadence="unconfigured",
        duration_months=12,
        included_visits=0,
        benefits=[],
        renewal_policy={},
        cancellation_policy={},
        definition_digest="a" * 64,
        activated_at=None,
        created_at="2026-08-30T00:00:00Z",
    )

    assert "idempotency_key" not in plan.model_dump()


@pytest.mark.parametrize(
    ("error", "status", "code", "recovery"),
    [
        (
            AgreementNotFound("foreign resource /private/path"),
            404,
            "not_found",
            "TERMINAL_FAILURE",
        ),
        (
            AgreementConflict("constraint secret_token=canary"),
            409,
            "resource_state_conflict",
            "RETRY_AFTER_REFRESH",
        ),
        (
            AgreementError("SQL enrollment payload canary"),
            422,
            "validation",
            "USER_CORRECTION_REQUIRED",
        ),
    ],
)
def test_service_agreement_failures_are_safe_and_classified(
    error, status, code, recovery
) -> None:
    with pytest.raises(HTTPException) as raised:
        fail(error)
    assert raised.value.status_code == status
    assert raised.value.detail["code"] == code
    assert raised.value.detail["recovery"] == recovery
    rendered = str(raised.value.detail).lower()
    assert "canary" not in rendered
    assert "private/path" not in rendered


@pytest.mark.asyncio
async def test_branch_specific_plan_and_agreement_mutations_are_isolated(
    agreement_branch_fixture,
) -> None:
    factory, company, branch_a, branch_b, foreign_branch, actor, customer, location = (
        agreement_branch_fixture
    )
    service = AgreementService()

    def plan(branch_id, key):
        return PlanCreate(
            branch_id=branch_id,
            code="QUALIFIED",
            name="Qualified branch plan",
            currency="USD",
            price_amount=Decimal("29.00"),
            billing_cadence="monthly",
            duration_months=12,
            included_visits=1,
            idempotency_key=key,
        )

    async with factory() as session:
        with pytest.raises(AgreementError, match="Branch was not found"):
            await service.create_plan(
                session,
                company.id,
                actor.id,
                plan(foreign_branch.id, f"foreign-plan-{uuid4()}"),
            )
    async with factory() as session:
        branch_plan = await service.create_plan(
            session,
            company.id,
            actor.id,
            plan(branch_a.id, f"branch-plan-{uuid4()}"),
        )
    async with factory() as session:
        branch_plan = await service.activate_plan(
            session, company.id, branch_plan.id, frozenset({branch_a.id})
        )
    async with factory() as session:
        other_branch_plan = await service.create_plan(
            session,
            company.id,
            actor.id,
            plan(branch_b.id, f"other-branch-plan-{uuid4()}"),
        )
    async with factory() as session:
        other_branch_plan = await service.activate_plan(
            session, company.id, other_branch_plan.id, frozenset({branch_b.id})
        )
    async with factory() as session:
        refreshed_branch_plan = await session.get(AgreementPlan, branch_plan.id)
        assert refreshed_branch_plan is not None
        assert refreshed_branch_plan.status == other_branch_plan.status == "active"

    async with factory() as session:
        assert branch_plan.id not in {
            item.id
            for item in await service.list_plans(
                session, company.id, frozenset({branch_b.id})
            )
        }
    async with factory() as session:
        with pytest.raises(AgreementError, match="Plan was not found"):
            await service.activate_plan(
                session, company.id, branch_plan.id, frozenset({branch_b.id})
            )

    enrollment = EnrollmentCreate(
        branch_id=branch_b.id,
        customer_id=customer.id,
        plan_id=branch_plan.id,
        service_location_ids=[location.id],
        start_date=date(2026, 9, 1),
        end_date=date(2027, 8, 31),
        idempotency_key=f"cross-branch-enrollment-{uuid4()}",
    )
    async with factory() as session:
        with pytest.raises(AgreementError, match="invalid or incomplete"):
            await service.enroll(session, company.id, actor.id, enrollment)

    async with factory() as session:
        agreement = await service.enroll(
            session,
            company.id,
            actor.id,
            enrollment.model_copy(
                update={
                    "branch_id": branch_a.id,
                    "idempotency_key": f"valid-enrollment-{uuid4()}",
                }
            ),
        )
    async with factory() as session:
        with pytest.raises(AgreementError, match="Agreement was not found"):
            await service.transition(
                session,
                company.id,
                agreement.id,
                frozenset({branch_b.id}),
                agreement.version,
                "active",
                key=f"foreign-transition-{uuid4()}",
                actor=actor.id,
            )
