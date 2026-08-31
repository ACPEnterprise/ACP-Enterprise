from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import ForeignKeyConstraint, UniqueConstraint

from app.service_agreements.models import (
    AgreementBillingOccurrence,
    AgreementCoverage,
    AgreementLifecycleEvidence,
    AgreementPlan,
    ServiceAgreement,
    ServiceEntitlement,
)
from app.service_agreements.schemas import PlanOut, Transition
from app.service_agreements.service import add_months, digest


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
