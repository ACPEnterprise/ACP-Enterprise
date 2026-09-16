from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FieldPurchaseSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class FieldPurchaseCreate(FieldPurchaseSchema):
    receipt_artifact_id: UUID
    inventory_location_id: UUID | None = None
    expected_assignment_version: int = Field(ge=1)
    idempotency_key: str = Field(
        min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"
    )


class ExtractedValue(FieldPurchaseSchema):
    value: str | Decimal | datetime | None
    confidence: Decimal = Field(ge=0, le=1)
    source: Literal["receipt_image", "operator"]


class ExtractedLine(FieldPurchaseSchema):
    line_number: int = Field(ge=1)
    description: str | None = Field(default=None, max_length=500)
    vendor_code: str | None = Field(default=None, max_length=160)
    quantity: Decimal = Field(gt=0)
    unit: str | None = Field(default=None, max_length=40)
    unit_price: Decimal | None = Field(default=None, ge=0)
    extended_amount: Decimal | None = Field(default=None, ge=0)
    confidence: dict[str, Decimal]


class FieldPurchaseExtractionInput(FieldPurchaseSchema):
    method: Literal["manual_review", "synthetic_fixture", "provider_adapter"]
    provider_reference: str | None = Field(default=None, max_length=160)
    vendor_id: UUID | None = None
    vendor: ExtractedValue | None = None
    transaction_reference: ExtractedValue | None = None
    purchased_at: ExtractedValue | None = None
    subtotal: ExtractedValue | None = None
    tax: ExtractedValue | None = None
    total: ExtractedValue | None = None
    currency: ExtractedValue | None = None
    lines: tuple[ExtractedLine, ...]
    extraction_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_version: int = Field(ge=1)

    @model_validator(mode="after")
    def unique_lines(self) -> "FieldPurchaseExtractionInput":
        numbers = [line.line_number for line in self.lines]
        if len(numbers) != len(set(numbers)):
            raise ValueError("line numbers must be unique")
        return self


class LineDispositionInput(FieldPurchaseSchema):
    line_id: UUID
    disposition: Literal[
        "used_on_this_job", "keep_on_truck", "return_or_unused", "non_inventory"
    ]
    quantity: Decimal = Field(gt=0)
    inventory_location_id: UUID | None = None
    reason: str | None = Field(default=None, max_length=500)
    idempotency_key: str = Field(
        min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"
    )


class FieldPurchaseDispositionInput(FieldPurchaseSchema):
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(
        min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"
    )
    dispositions: tuple[LineDispositionInput, ...] = Field(min_length=1)


class FieldPurchaseLineOut(FieldPurchaseSchema):
    id: UUID
    line_number: int
    description: str | None
    vendor_code: str | None
    quantity: Decimal
    unit: str | None
    unit_price: Decimal | None
    extended_amount: Decimal | None
    inventory_item_id: UUID | None
    match_state: str


class FieldPurchaseDispositionOut(FieldPurchaseSchema):
    line_id: UUID
    disposition: str
    quantity: Decimal
    inventory_location_id: UUID | None
    state: str


class FieldPurchaseOut(FieldPurchaseSchema):
    id: UUID
    job_id: UUID
    employee_id: UUID
    receipt_artifact_id: UUID
    receipt_digest: str
    state: str
    version: int
    extraction_method: str | None
    extraction_digest: str | None
    lines: tuple[FieldPurchaseLineOut, ...]
    dispositions: tuple[FieldPurchaseDispositionOut, ...]
    created_at: datetime


class VendorMappingCreate(FieldPurchaseSchema):
    vendor_id: UUID
    vendor_code: str = Field(min_length=1, max_length=160)
    inventory_item_id: UUID
    expected_prior_mapping_id: UUID | None = None
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class FieldPurchaseReviewSummary(FieldPurchaseSchema):
    id: UUID
    job_id: UUID
    state: str
    unmatched_lines: int
    pending_dispositions: int
    receipt_total_reconciles: bool | None
    blocker_codes: tuple[str, ...]
    created_at: datetime
