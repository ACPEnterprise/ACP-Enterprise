from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EstimateSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class EstimateLineInput(EstimateSchema):
    snapshot_id: UUID
    title: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=4000)


class ProposalInput(EstimateSchema):
    branch_id: UUID
    customer_id: UUID
    service_location_id: UUID | None = None
    proposal_title: str = Field(min_length=1, max_length=240)
    customer_message: str | None = Field(default=None, max_length=4000)
    terms: str | None = Field(default=None, max_length=8000)
    expires_at: datetime | None = None
    lines: tuple[EstimateLineInput, ...] = Field(min_length=1)
    discount_type: str | None = Field(default=None, pattern=r"^(fixed|percentage)$")
    discount_value: Decimal | None = Field(default=None, ge=0)


class RevisionInput(ProposalInput):
    expected_version: int = Field(ge=1)


class TransitionInput(EstimateSchema):
    branch_id: UUID
    expected_version: int = Field(ge=1)
    occurred_at: datetime


class DecisionInput(TransitionInput):
    customer_name: str = Field(min_length=1, max_length=240)
    customer_email: str | None = Field(default=None, max_length=320)
    customer_comment: str | None = Field(default=None, max_length=4000)
    rejection_reason: str | None = Field(default=None, max_length=4000)
    evidence_reference: str | None = Field(default=None, max_length=500)


class TaxPolicyInput(EstimateSchema):
    branch_id: UUID | None = None
    tax_classification_id: UUID
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    rate_basis_points: int = Field(ge=0, le=10000)
    version: int = Field(default=1, ge=1)
    effective_at: datetime
    expires_at: datetime | None = None


class EstimateLineItem(EstimateSchema):
    id: UUID
    position: int
    title: str
    description: str | None
    snapshot_id: UUID
    snapshot_digest: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal
    currency: str
    option_group_id: UUID | None
    option_id: UUID | None
    discount_allocation: Decimal
    discounted_basis: Decimal
    tax_amount: Decimal
    taxable: bool


class EstimateRevisionItem(EstimateSchema):
    id: UUID
    parent_revision_id: UUID | None
    revision_number: int
    status: str
    proposal_title: str
    customer_message: str | None
    terms: str | None
    currency: str
    subtotal_amount: Decimal
    discount_type: str | None
    discount_value: Decimal | None
    discount_amount: Decimal
    taxable_basis: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    expires_at: datetime | None
    created_at: datetime
    lines: tuple[EstimateLineItem, ...]


class EstimateItem(EstimateSchema):
    id: UUID
    company_id: UUID
    branch_id: UUID
    customer_id: UUID
    service_location_id: UUID | None
    estimate_number: str
    status: str
    acceptance_status: str
    version: int
    current_revision: EstimateRevisionItem
    customer_decision: object | None


class TaxPolicyItem(EstimateSchema):
    id: UUID
    company_id: UUID
    branch_id: UUID | None
    tax_classification_id: UUID
    currency: str
    rate_basis_points: int
    version: int
    effective_at: datetime
    expires_at: datetime | None
