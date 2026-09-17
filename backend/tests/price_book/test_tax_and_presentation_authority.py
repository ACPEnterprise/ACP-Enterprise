from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.price_book.commerce_contracts import (
    AuthoritativeSellableReference,
    CommerceIntelligenceHandoff,
    PricingTierReference,
    SalesPresentationAlternative,
    build_authority_digest,
)
from app.tax_policy.company_policy import (
    customer_treatment,
    effective_company_tax_policy,
)
from app.tax_policy.models import CompanyTaxPolicy


def policy(**overrides: object) -> CompanyTaxPolicy:
    values = {
        "company_id": uuid4(),
        "policy_identity": "ALL_COUNTY_OPERATING_POLICY",
        "version": 1,
        "status": "certified",
        "effective_at": datetime.now(timezone.utc),
        "customer_service_treatment": "NOT_TAXED",
        "customer_material_treatment": "NOT_TAXED",
        "purchase_material_tax_handling": "PAID_AT_PURCHASE",
        "authority_source": "OWNER_OPERATIONAL_POLICY",
        "authorized_exceptions": [],
        "created_by_user_id": uuid4(),
    }
    values.update(overrides)
    return CompanyTaxPolicy(**values)


def test_customer_and_purchase_side_tax_authority_remain_separate() -> None:
    item = policy()
    assert (
        customer_treatment(item, component_types={"labor", "material"}) == "NOT_TAXED"
    )
    assert item.purchase_material_tax_handling == "PAID_AT_PURCHASE"


def test_authorized_service_exception_fails_closed() -> None:
    service_id = uuid4()
    item = policy(
        authorized_exceptions=[
            {"scope": "SERVICE_ITEM", "service_item_id": str(service_id)}
        ]
    )
    assert (
        customer_treatment(item, component_types={"labor"}, service_item_id=service_id)
        == "REVIEW_REQUIRED"
    )


@pytest.mark.asyncio
async def test_ambiguous_effective_company_policy_fails_closed() -> None:
    effective = datetime.now(timezone.utc)
    policies = [policy(effective_at=effective), policy(effective_at=effective)]

    class Result:
        def all(self):
            return policies

    class Session:
        async def scalars(self, _query):
            return Result()

    with pytest.raises(ValueError, match="ambiguous"):
        await effective_company_tax_policy(
            Session(), company_id=policies[0].company_id, effective_at=effective
        )


def test_good_better_best_is_not_a_pricing_tier() -> None:
    component = AuthoritativeSellableReference(
        service_item_id=uuid4(), price_version_id=uuid4()
    )
    alternative = SalesPresentationAlternative(
        presentation_label="GOOD", authoritative_components=(component,)
    )
    assert alternative.pricing_tier is None
    tiered = SalesPresentationAlternative(
        presentation_label="Custom package",
        authoritative_components=(component,),
        pricing_tier=PricingTierReference(
            pricing_tier_id=uuid4(), pricing_tier_version_id=uuid4()
        ),
    )
    assert tiered.presentation_label != str(tiered.pricing_tier.pricing_tier_id)


def test_intelligence_cannot_select_or_accept_presentation() -> None:
    component = AuthoritativeSellableReference(
        service_item_id=uuid4(), price_version_id=uuid4()
    )
    with pytest.raises(ValidationError):
        SalesPresentationAlternative(
            presentation_label="BETTER",
            authoritative_components=(component,),
            suggested_by_intelligence=True,
            selected_by_technician=True,
        )


def test_handoff_is_read_only_and_digest_is_deterministic() -> None:
    company_id, branch_id = uuid4(), uuid4()
    base = AuthoritativeSellableReference(
        service_item_id=uuid4(), price_version_id=uuid4()
    )
    digest = build_authority_digest(
        company_id=company_id,
        branch_id=branch_id,
        base_solution=base,
        eligible_components=(),
    )
    handoff = CommerceIntelligenceHandoff(
        company_id=company_id,
        branch_id=branch_id,
        base_solution=base,
        eligible_components=(),
        alternatives=(),
        authority_digest=digest,
    )
    assert digest == build_authority_digest(
        company_id=company_id,
        branch_id=branch_id,
        base_solution=base,
        eligible_components=(),
    )
    assert not handoff.mutation_authorized
    assert not handoff.autonomous_repricing_authorized
    assert not handoff.autonomous_activation_authorized
