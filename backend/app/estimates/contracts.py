from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class EstimateLineSpec:
    snapshot_id: UUID
    title: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class CreateEstimateSpec:
    company_id: UUID
    branch_id: UUID
    customer_id: UUID
    service_location_id: UUID | None
    actor_user_id: UUID
    proposal_title: str
    customer_message: str | None
    terms: str | None
    expires_at: datetime | None
    lines: tuple[EstimateLineSpec, ...]


@dataclass(frozen=True, slots=True)
class EstimateLineRecord:
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


@dataclass(frozen=True, slots=True)
class EstimateRevisionRecord:
    id: UUID
    revision_number: int
    status: str
    proposal_title: str
    customer_message: str | None
    terms: str | None
    currency: str
    subtotal_amount: Decimal
    total_amount: Decimal
    expires_at: datetime | None
    created_at: datetime
    lines: tuple[EstimateLineRecord, ...]


@dataclass(frozen=True, slots=True)
class EstimateRecord:
    id: UUID
    company_id: UUID
    branch_id: UUID
    customer_id: UUID
    service_location_id: UUID | None
    estimate_number: str
    status: str
    acceptance_status: str
    version: int
    current_revision: EstimateRevisionRecord
