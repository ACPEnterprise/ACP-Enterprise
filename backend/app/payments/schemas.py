from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CollectInput(BaseModel):
    branch_id: UUID
    customer_id: UUID
    invoice_id: UUID | None = None
    amount: Decimal = Field(gt=0, decimal_places=2)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    opaque_payment_method: str = Field(pattern=r"^opaque_[A-Za-z0-9_.:-]+$", max_length=255)
    idempotency_key: str = Field(min_length=8, max_length=120)


class ApplyInput(BaseModel):
    branch_id: UUID
    invoice_id: UUID
    amount: Decimal = Field(gt=0, decimal_places=2)
    expected_invoice_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=120)
    occurred_at: datetime


class RefundInput(BaseModel):
    branch_id: UUID
    amount: Decimal = Field(gt=0, decimal_places=2)
    reason: str = Field(min_length=1, max_length=500)
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=120)


class IntentItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    branch_id: UUID
    customer_id: UUID
    invoice_id: UUID | None
    amount: Decimal
    currency: str
    status: str
    version: int


class ReceiptItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    branch_id: UUID
    customer_id: UUID
    intent_id: UUID
    currency: str
    status: str
    captured_amount: Decimal
    available_amount: Decimal
    applied_amount: Decimal
    refunded_amount: Decimal
    disputed_amount: Decimal
    version: int
    captured_at: datetime


class RefundItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    receipt_id: UUID
    amount: Decimal
    currency: str
    status: str
    reason: str
