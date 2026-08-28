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
    created_at: datetime
    updated_at: datetime
    lines: tuple[PurchaseOrderLineItem, ...] = ()
    issuance_digest: str | None = None


class PurchasingWorkspace(PurchasingSchema):
    vendors: tuple[VendorItem, ...]
    purchase_orders: tuple[PurchaseOrderItem, ...]
