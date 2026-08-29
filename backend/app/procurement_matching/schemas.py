from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MatchSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class EvaluateMatchCommand(MatchSchema):
    purchase_order_id: UUID
    vendor_bill_id: UUID
    expected_purchase_order_version: int = Field(ge=1)
    expected_bill_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)


class MatchLineItem(MatchSchema):
    id: UUID
    purchase_order_line_id: UUID
    receipt_line_id: UUID | None
    bill_line_id: UUID
    inventory_item_id: UUID | None
    ordered_quantity: Decimal
    received_quantity: Decimal
    returned_quantity: Decimal
    net_accepted_quantity: Decimal
    billed_quantity: Decimal
    po_unit_cost: Decimal
    billed_unit_cost: Decimal
    quantity_variance: Decimal
    price_variance: Decimal
    state: str
    evidence_digest: str


class MatchExceptionItem(MatchSchema):
    id: UUID
    match_line_id: UUID | None
    category: str
    status: str
    expected_evidence: str
    actual_evidence: str
    resolution: str | None
    resolution_note: str | None
    version: int


class MatchItem(MatchSchema):
    id: UUID
    company_id: UUID
    branch_id: UUID
    purchase_order_id: UUID
    vendor_bill_id: UUID
    state: str
    admission_state: str
    policy_reference: str | None
    purchase_order_version: int
    bill_version: int
    evidence_digest: str
    evaluated_by_user_id: UUID
    evaluated_at: datetime
    version: int
    lines: tuple[MatchLineItem, ...] = ()
    exceptions: tuple[MatchExceptionItem, ...] = ()


class ResolveMatchExceptionCommand(MatchSchema):
    expected_match_version: int = Field(ge=1)
    expected_exception_version: int = Field(ge=1)
    resolution: str = Field(
        pattern=r"^(accept_variance|request_vendor_credit|hold_bill|reject_bill|wait_for_receipt|wait_for_bill|correct_future_po|return_goods|manual_review_required)$"
    )
    note: str = Field(min_length=1, max_length=1000)
    idempotency_key: str = Field(min_length=1, max_length=128)


class VendorPerformanceItem(MatchSchema):
    vendor_id: UUID
    purchase_order_count: int
    ordered_quantity: Decimal
    accepted_received_quantity: Decimal
    returned_quantity: Decimal
    net_accepted_quantity: Decimal
    fulfillment_ratio: Decimal | None
    return_ratio: Decimal | None
    completed_lead_time_samples: int
    average_lead_time_days: Decimal | None
    discrepancy_count: int
    price_variance_line_count: int
    evidence_digest: str


class VendorPerformanceReport(MatchSchema):
    definition_version: int
    company_id: UUID
    branch_id: UUID | None
    evaluated_at: datetime
    items: tuple[VendorPerformanceItem, ...]
    evidence_digest: str
