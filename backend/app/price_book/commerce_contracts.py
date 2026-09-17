import hashlib
import json
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class AuthoritativeSellableReference(BaseModel):
    service_item_id: UUID
    price_version_id: UUID
    option_group_id: UUID | None = None
    option_id: UUID | None = None


class PricingTierReference(BaseModel):
    """A controlled commercial tier, never a presentation label or discount."""

    pricing_tier_id: UUID
    pricing_tier_version_id: UUID


class SalesPresentationAlternative(BaseModel):
    presentation_label: Literal["GOOD", "BETTER", "BEST"] | str
    authoritative_components: tuple[AuthoritativeSellableReference, ...] = Field(
        min_length=1
    )
    pricing_tier: PricingTierReference | None = None
    membership_entitlement_id: UUID | None = None
    suggested_by_intelligence: bool = False
    selected_by_technician: bool = False
    accepted_by_customer: bool = False

    @model_validator(mode="after")
    def lock_authority_boundaries(self):
        if self.suggested_by_intelligence and (
            self.selected_by_technician or self.accepted_by_customer
        ):
            raise ValueError(
                "Intelligence suggestions cannot select or accept a sales presentation."
            )
        return self


class CommerceIntelligenceHandoff(BaseModel):
    company_id: UUID
    branch_id: UUID
    base_solution: AuthoritativeSellableReference
    eligible_components: tuple[AuthoritativeSellableReference, ...]
    alternatives: tuple[SalesPresentationAlternative, ...]
    authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    mutation_authorized: Literal[False] = False
    autonomous_repricing_authorized: Literal[False] = False
    autonomous_activation_authorized: Literal[False] = False


def build_authority_digest(
    *,
    company_id: UUID,
    branch_id: UUID,
    base_solution: AuthoritativeSellableReference,
    eligible_components: tuple[AuthoritativeSellableReference, ...],
) -> str:
    payload = {
        "company_id": str(company_id),
        "branch_id": str(branch_id),
        "base_solution": base_solution.model_dump(mode="json"),
        "eligible_components": [
            item.model_dump(mode="json") for item in eligible_components
        ],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
