from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class PlanCreate(Schema):
    branch_id: UUID | None = None
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    currency: str = Field(pattern="^[A-Z]{3}$")
    price_amount: Decimal | None = Field(default=None, ge=0)
    billing_cadence: str
    duration_months: int = Field(gt=0)
    included_visits: int = Field(ge=0)
    benefits: list[dict[str, object]] = []
    renewal_policy: dict[str, object] = {}
    cancellation_policy: dict[str, object] = {}


class PlanOut(PlanCreate):
    id: UUID
    company_id: UUID
    version: int
    status: str
    definition_digest: str
    activated_at: datetime | None
    created_at: datetime


class EnrollmentCreate(Schema):
    branch_id: UUID
    customer_id: UUID
    plan_id: UUID
    service_location_ids: list[UUID] = Field(min_length=1)
    start_date: date
    end_date: date
    idempotency_key: str = Field(min_length=1, max_length=160)


class AgreementOut(Schema):
    id: UUID
    company_id: UUID
    branch_id: UUID
    customer_id: UUID
    plan_id: UUID
    agreement_number: str
    status: str
    start_date: date
    end_date: date
    plan_snapshot: dict[str, object]
    evidence_digest: str
    version: int
    cancellation_reason: str | None
    created_at: datetime
    updated_at: datetime


class Transition(Schema):
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=160)
    reason: str | None = Field(default=None, max_length=2000)


class EntitlementOut(Schema):
    id: UUID
    company_id: UUID
    branch_id: UUID
    agreement_id: UUID
    service_location_id: UUID
    sequence: int
    service_category: str
    eligible_from: date
    eligible_to: date
    status: str
    appointment_id: UUID | None
    job_id: UUID | None
    source_digest: str
    created_at: datetime


class WorkspaceOut(Schema):
    agreements: list[AgreementOut]
    entitlements: list[EntitlementOut]
    active_count: int
    renewal_pending_count: int
    service_due_count: int
    billing_unconfigured_count: int
