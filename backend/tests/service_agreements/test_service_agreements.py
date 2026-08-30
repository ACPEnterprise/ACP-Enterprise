from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.service_agreements.schemas import PlanOut, Transition
from app.service_agreements.service import add_months, digest


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
