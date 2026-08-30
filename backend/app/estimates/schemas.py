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


class EstimateSummary(EstimateSchema):
    id: UUID
    branch_id: UUID
    customer_id: UUID
    service_location_id: UUID | None
    estimate_number: str
    status: str
    acceptance_status: str
    version: int
    proposal_title: str
    currency: str
    total_amount: Decimal
    expires_at: datetime | None
    updated_at: datetime


class EstimateList(EstimateSchema):
    items: tuple[EstimateSummary, ...]
    total: int


class EstimateArtifact(EstimateSchema):
    schema_version: int
    template_version: str
    estimate_id: UUID
    estimate_version: int
    revision_id: UUID
    revision_number: int
    status: str
    artifact_digest: str
    filename: str
    media_type: str
    content: str


class CommercialPolicyWrite(EstimateSchema):
    branch_id: UUID
    policy_type: str = Field(
        pattern=r"^(discount|price_override|estimate_expiration|rounding|tax_readiness|document_template|delivery_readiness|follow_up_cadence)$"
    )
    status: str = Field(pattern=r"^(unconfigured|draft|active|inactive)$")
    configuration: dict[str, object] = {}
    readiness_reason: str = Field(min_length=1, max_length=500)
    expected_version: int | None = Field(default=None, ge=1)
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9._:-]{8,128}$")


class CommercialPolicyItem(EstimateSchema):
    id: UUID
    company_id: UUID
    branch_id: UUID
    policy_type: str
    status: str
    configuration: dict[str, object]
    readiness_reason: str
    version: int
    evidence_digest: str
    created_by_user_id: UUID
    created_at: datetime


class PresentationPrepareInput(EstimateSchema):
    branch_id: UUID
    recipient_reference: str = Field(min_length=1, max_length=320)
    channel: str = Field(pattern=r"^(protected_link|print|email_preparation|sms_preparation)$")
    expires_at: datetime | None = None
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9._:-]{8,128}$")


class PresentationAuthorityItem(EstimateSchema):
    id: UUID
    estimate_id: UUID
    revision_id: UUID
    revision_number: int
    estimate_version: int
    artifact_digest: str
    recipient_reference: str
    channel: str
    status: str
    expires_at: datetime | None
    evidence_digest: str
    created_at: datetime
    viewed_at: datetime | None


class PresentationCredential(PresentationAuthorityItem):
    access_token: str


class ProtectedEstimateView(EstimateSchema):
    presentation: PresentationAuthorityItem
    artifact: EstimateArtifact


class ProtectedEstimateDecision(EstimateSchema):
    revision_id: UUID
    decision: str = Field(pattern=r"^(approve|reject)$")
    customer_name: str = Field(min_length=1, max_length=240)
    customer_email: str | None = Field(default=None, max_length=320)
    customer_comment: str | None = Field(default=None, max_length=4000)
    rejection_reason: str | None = Field(default=None, max_length=4000)
    occurred_at: datetime


class FollowUpWrite(EstimateSchema):
    branch_id: UUID
    assigned_user_id: UUID
    state: str = Field(pattern=r"^(open|snoozed|completed|canceled)$")
    due_at: datetime | None = None
    disposition: str | None = Field(default=None, max_length=240)
    occurred_at: datetime
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9._:-]{8,128}$")


class FollowUpItem(EstimateSchema):
    id: UUID
    branch_id: UUID
    estimate_id: UUID
    revision_id: UUID
    assigned_user_id: UUID
    state: str
    due_at: datetime | None
    disposition: str | None
    sequence: int
    evidence_digest: str
    occurred_at: datetime


class CommercialReport(EstimateSchema):
    created: int
    presented: int
    viewed: int
    accepted: int
    rejected: int
    expired: int
    accepted_not_converted: int
    converted: int
    accepted_value_by_currency: dict[str, Decimal]
    outstanding_value_by_currency: dict[str, Decimal]


class CommercialHistoryItem(EstimateSchema):
    evidence_type: str
    state: str
    occurred_at: datetime
    actor_reference: UUID | None
    revision_id: UUID | None
    evidence_digest: str | None
    detail: str | None


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
