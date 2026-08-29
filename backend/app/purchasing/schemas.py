from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PurchasingSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class Command(PurchasingSchema):
    idempotency_key: str = Field(min_length=1, max_length=128)


class VendorCreate(Command):
    code: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=200)
    legal_name: str | None = Field(default=None, max_length=240)
    contact_reference: str | None = Field(default=None, max_length=240)
    provenance_reference: str | None = Field(default=None, max_length=200)


class VendorUpdate(Command):
    expected_version: int = Field(ge=1)
    display_name: str = Field(min_length=1, max_length=200)
    legal_name: str | None = Field(default=None, max_length=240)
    contact_reference: str | None = Field(default=None, max_length=240)
    status: str


class VendorItem(PurchasingSchema):
    id: UUID
    company_id: UUID
    code: str
    display_name: str
    legal_name: str | None
    contact_reference: str | None
    status: str
    provenance_type: str
    provenance_reference: str | None
    version: int
    created_at: datetime
    updated_at: datetime


class VendorPerformanceEvidence(PurchasingSchema):
    schema_version: int = 1
    evidence_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_type: str
    availability: str = Field(
        pattern=r"^(available|unavailable|not_applicable|conflicting)$"
    )
    value: str | None
    unit: str | None
    company_id: UUID
    branch_id: UUID
    vendor_id: UUID
    purchase_order_id: UUID
    purchase_order_line_id: UUID | None = None
    receipt_id: UUID | None = None
    discrepancy_id: UUID | None = None
    return_id: UUID | None = None
    source_type: str
    source_id: UUID
    effective_at: datetime
    provenance: tuple[str, ...]
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class VendorPerformanceSummary(PurchasingSchema):
    purchase_orders_observed: int
    receipts_observed: int
    discrepancies_observed: int
    returns_observed: int
    ordered_quantity_observed: Decimal
    accepted_quantity_observed: Decimal
    rejected_quantity_observed: Decimal
    lead_time_observations: int
    availability_counts: dict[str, int]


class VendorPerformanceEvidenceReport(PurchasingSchema):
    schema_version: int = 1
    company_id: UUID
    vendor_id: UUID
    from_at: datetime | None
    to_at: datetime | None
    evidence: tuple[VendorPerformanceEvidence, ...]
    summary: VendorPerformanceSummary
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReplenishmentTarget(PurchasingSchema):
    branch_id: UUID
    inventory_item_id: UUID
    target_available_quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=6)


class ReplenishmentWorkbenchRequest(PurchasingSchema):
    as_of: datetime
    targets: tuple[ReplenishmentTarget, ...] = Field(min_length=1)


class ReplenishmentRecommendation(PurchasingSchema):
    branch_id: UUID
    inventory_item_id: UUID
    item_code: str
    item_name: str
    stocking_unit: str
    target_available_quantity: Decimal
    on_hand_quantity: Decimal
    reserved_quantity: Decimal
    available_quantity: Decimal
    open_purchase_order_quantity: Decimal
    recommended_order_quantity: Decimal
    recommendation_state: str = Field(pattern=r"^(recommend_order|no_action)$")
    provenance: tuple[str, ...]
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReplenishmentWorkbench(PurchasingSchema):
    schema_version: int = 1
    company_id: UUID
    as_of: datetime
    recommendations: tuple[ReplenishmentRecommendation, ...]
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class PurchaseOrderCreate(Command):
    branch_id: UUID
    vendor_id: UUID
    po_number: str = Field(min_length=1, max_length=80)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    expected_date: date | None = None


class PurchaseOrderUpdate(Command):
    expected_version: int = Field(ge=1)
    vendor_id: UUID
    expected_date: date | None = None


class PurchaseOrderLineWrite(Command):
    expected_po_version: int = Field(ge=1)
    inventory_item_id: UUID | None = None
    description: str = Field(default="", max_length=1000)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=6)
    unit: str = Field(min_length=1, max_length=40)
    unit_cost: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    expected_date: date | None = None

    @model_validator(mode="after")
    def require_identity(self) -> "PurchaseOrderLineWrite":
        if self.inventory_item_id is None and not self.description.strip():
            raise ValueError("Inventory item or free description is required")
        return self


class PurchaseOrderLineUpdate(PurchaseOrderLineWrite):
    expected_line_version: int = Field(ge=1)


class TransitionCommand(Command):
    expected_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=500)


class PurchaseOrderLineItem(PurchasingSchema):
    id: UUID
    line_number: int
    inventory_item_id: UUID | None
    description: str
    quantity: Decimal
    unit: str
    unit_cost: Decimal
    extended_cost: Decimal
    expected_date: date | None
    version: int
    is_cancelled: bool = False
    cumulative_accepted_quantity: Decimal = Decimal(0)
    outstanding_quantity: Decimal = Decimal(0)


class ReceiptLineCommand(PurchasingSchema):
    purchase_order_line_id: UUID
    accepted_quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=6)
    rejected_quantity: Decimal = Field(
        default=Decimal(0), ge=0, max_digits=18, decimal_places=6
    )
    discrepancy_category: str | None = None
    observed_condition: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def require_outcome(self) -> "ReceiptLineCommand":
        if (
            self.accepted_quantity + self.rejected_quantity <= 0
            and not self.discrepancy_category
        ):
            raise ValueError("Receipt line requires quantity or discrepancy evidence")
        if self.rejected_quantity > 0 and not self.discrepancy_category:
            raise ValueError("Rejected quantity requires discrepancy evidence")
        return self


class RecordReceiptCommand(Command):
    expected_po_version: int = Field(ge=1)
    receiving_event_identity: str = Field(min_length=1, max_length=128)
    received_at: datetime
    effective_date: date
    source_reference: str | None = Field(default=None, max_length=240)
    lines: tuple[ReceiptLineCommand, ...] = Field(min_length=1)


class ResolveDiscrepancyCommand(Command):
    expected_po_version: int = Field(ge=1)
    expected_discrepancy_version: int = Field(ge=1)
    resolution: str = Field(pattern=r"^(resolved_accepted|resolved_rejected)$")
    note: str = Field(min_length=1, max_length=1000)


class ReceiptLineItem(PurchasingSchema):
    id: UUID
    purchase_order_line_id: UUID
    ordered_quantity_snapshot: Decimal
    accepted_quantity: Decimal
    rejected_quantity: Decimal
    cumulative_accepted_quantity: Decimal
    outstanding_quantity: Decimal
    unit_snapshot: str
    discrepancy_category: str | None
    observed_condition: str | None


class ReceiptItem(PurchasingSchema):
    id: UUID
    receiving_event_identity: str
    status: str
    receiver_user_id: UUID
    received_at: datetime
    effective_date: date
    source_reference: str | None
    lines: tuple[ReceiptLineItem, ...] = ()


class DiscrepancyItem(PurchasingSchema):
    id: UUID
    purchase_order_line_id: UUID
    receipt_id: UUID
    category: str
    status: str
    expected_fact: str
    actual_fact: str
    observed_condition: str
    opened_by_user_id: UUID
    opened_at: datetime
    resolved_by_user_id: UUID | None
    resolved_at: datetime | None
    resolution_note: str | None
    version: int


class CreatePurchaseReturnCommand(Command):
    expected_po_version: int = Field(ge=1)
    return_identity: str = Field(min_length=1, max_length=128)
    receipt_id: UUID
    receipt_line_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=6)
    reason: str
    reason_note: str | None = Field(default=None, max_length=1000)
    authorization_required: bool
    effective_date: date
    source_reference: str | None = Field(default=None, max_length=240)


class PurchaseReturnTransitionCommand(Command):
    expected_po_version: int = Field(ge=1)
    expected_return_version: int = Field(ge=1)
    vendor_authorization_reference: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=1000)
    occurred_at: datetime


class PurchaseReturnItem(PurchasingSchema):
    id: UUID
    purchase_order_id: UUID
    vendor_id: UUID
    receipt_id: UUID
    receipt_line_id: UUID
    purchase_order_line_id: UUID
    return_identity: str
    item_identity_snapshot: str
    accepted_quantity_snapshot: Decimal
    quantity: Decimal
    remaining_returnable_quantity: Decimal = Decimal(0)
    reason: str
    reason_note: str | None
    status: str
    authorization_status: str
    vendor_authorization_reference: str | None
    vendor_instructions: str | None
    requested_by_user_id: UUID
    requested_at: datetime
    effective_date: date
    authorization_at: datetime | None
    returned_at: datetime | None
    vendor_received_at: datetime | None
    closed_at: datetime | None
    canceled_at: datetime | None
    source_reference: str | None
    version: int


class PurchaseOrderItem(PurchasingSchema):
    id: UUID
    company_id: UUID
    branch_id: UUID
    vendor_id: UUID
    po_number: str
    status: str
    currency: str
    expected_date: date | None
    prepared_by_user_id: UUID
    submitted_by_user_id: UUID | None
    approved_by_user_id: UUID | None
    issued_by_user_id: UUID | None
    lifecycle_reason: str | None
    version: int
    effective_revision: int = 1
    created_at: datetime
    updated_at: datetime
    lines: tuple[PurchaseOrderLineItem, ...] = ()
    issuance_digest: str | None = None
    receiving_status: str = "not_received"
    receipts: tuple[ReceiptItem, ...] = ()
    discrepancies: tuple[DiscrepancyItem, ...] = ()
    returns: tuple[PurchaseReturnItem, ...] = ()
    change_orders: tuple["PurchaseOrderChangeItem", ...] = ()
    revisions: tuple["PurchaseOrderRevisionItem", ...] = ()
    disposition: "PurchaseOrderDispositionItem | None" = None


class PurchaseOrderChangeOperation(PurchasingSchema):
    operation: str = Field(
        pattern=r"^(set_quantity|set_unit_cost|cancel_line|add_line|set_expected_date)$"
    )
    line_id: UUID | None = None
    inventory_item_id: UUID | None = None
    description: str | None = Field(default=None, max_length=1000)
    quantity: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=6
    )
    unit: str | None = Field(default=None, max_length=40)
    unit_cost: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=4
    )
    expected_date: date | None = None


class RequestPurchaseOrderChangeCommand(Command):
    expected_po_version: int = Field(ge=1)
    base_revision: int = Field(ge=1)
    change_identity: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=1000)
    changes: tuple[PurchaseOrderChangeOperation, ...] = Field(min_length=1)


class DecidePurchaseOrderChangeCommand(Command):
    expected_po_version: int = Field(ge=1)
    expected_base_revision: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=1000)


class PurchaseOrderChangeItem(PurchasingSchema):
    id: UUID
    change_identity: str
    base_revision: int
    proposed_changes: list[dict[str, object]]
    reason: str
    status: str
    requested_by_user_id: UUID
    requested_at: datetime
    decided_by_user_id: UUID | None
    decided_at: datetime | None
    effective_revision: int | None
    evidence_digest: str
    downstream_reconciliation_required: bool


class PurchaseOrderRevisionItem(PurchasingSchema):
    id: UUID
    revision_number: int
    predecessor_revision: int | None
    change_order_id: UUID | None
    effective_snapshot: dict[str, object]
    evidence_digest: str
    effective_by_user_id: UUID
    effective_at: datetime


class PurchaseOrderDispositionCommand(Command):
    expected_po_version: int = Field(ge=1)
    expected_effective_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)
    confirm_terminal_action: bool


class PurchaseOrderDispositionItem(PurchasingSchema):
    id: UUID
    purchase_order_version: int
    effective_revision: int
    prior_status: str
    disposition: str
    reason: str
    quantity_evidence: list[dict[str, object]]
    evidence_digest: str
    actor_user_id: UUID
    occurred_at: datetime


class PurchasingWorkspace(PurchasingSchema):
    vendors: tuple[VendorItem, ...]
    purchase_orders: tuple[PurchaseOrderItem, ...]
