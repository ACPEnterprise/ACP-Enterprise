from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ConfidenceResponse(BaseModel):
    status: Literal["measured", "estimated", "unknown"]
    percentage: int = Field(ge=0, le=100)
    explanation: str


class EvidenceReferenceResponse(BaseModel):
    kind: Literal["business_event", "source_record", "allocation", "reasoning"]
    reference_id: str
    source_system: str
    source_version: str
    source_record_type: str
    content_digest: str
    observed_at: datetime
    explanation: str


class ProfitMeasurementResponse(BaseModel):
    id: UUID
    company_id: UUID
    branch_id: UUID | None
    subject_type: str
    subject_id: UUID
    period_start: date
    period_end: date
    currency: str
    revenue_minor: int | None
    labor_minor: int | None
    materials_minor: int | None
    equipment_minor: int | None
    truck_minor: int | None
    overhead_minor: int | None
    gross_profit_minor: int | None
    net_profit_minor: int | None
    confidence: ConfidenceResponse
    evidence: list[EvidenceReferenceResponse]
    input_fact_ids: list[UUID]
    input_allocation_ids: list[UUID]
    input_digest: str
    engine_version: str
    version: int
    measured_at: datetime


class ProfitMeasurementListResponse(BaseModel):
    items: list[ProfitMeasurementResponse]
    limit: int
    offset: int


class BusinessFactResponse(BaseModel):
    id: UUID
    company_id: UUID
    branch_id: UUID | None
    subject_type: str
    subject_id: UUID
    category: Literal["revenue", "labor", "materials", "equipment", "truck", "overhead"]
    fact_key: str
    amount_minor: int | None
    currency: str
    confidence: ConfidenceResponse
    evidence: list[EvidenceReferenceResponse]
    period_start: date
    period_end: date
    measurement_method: str
    accounting_basis: Literal["accrual", "cash", "operational"]
    correction_kind: Literal["original", "reversal", "supersession", "effective_date"]
    corrects_fact_id: UUID | None
    input_digest: str
    effective_at: datetime
    version: int
    recorded_at: datetime


class BusinessFactListResponse(BaseModel):
    items: list[BusinessFactResponse]
    limit: int
    offset: int


class ProfitabilityProjectionResponse(BaseModel):
    scope_type: Literal["branch", "company"]
    scope_id: UUID
    currency: str | None
    measurement_count: int
    revenue_minor: int | None
    labor_minor: int | None
    materials_minor: int | None
    equipment_minor: int | None
    truck_minor: int | None
    overhead_minor: int | None
    gross_profit_minor: int | None
    net_profit_minor: int | None
    confidence: ConfidenceResponse
    as_of: datetime | None


class EvidenceCompletenessResponse(BaseModel):
    company_id: UUID
    known_fact_count: int
    linked_fact_count: int
    missing_evidence_count: int
    completeness_percentage: int


class StaleMeasurementResponse(BaseModel):
    measurement_id: UUID
    subject_type: str
    subject_id: UUID
    measured_at: datetime
    stale_since: datetime


class CloseReadinessResponse(BaseModel):
    period_id: UUID
    responsible_owner_id: UUID
    ready: bool
    checks: dict[str, object]
    blockers: list[str]
    input_digest: str
    version: int
    evaluated_at: datetime


class ReconciliationStatusResponse(BaseModel):
    period_id: UUID
    economics: dict[str, str]
    general_ledger_status: Literal["passed", "failed", "unknown"]
    period_variance_minor: int | None
    unexplained_residual_minor: int | None
    reconciled_at: datetime | None


class AllocationStatusResponse(BaseModel):
    period_id: UUID
    run_count: int
    balanced_run_count: int
    residual_minor: int


class AuditPackageResponse(BaseModel):
    id: UUID
    period_id: UUID
    manifest: dict[str, object]
    package_digest: str
    version: int
    created_at: datetime


class ExportStatusResponse(BaseModel):
    id: UUID
    period_id: UUID
    export_key: str
    status: Literal["prepared", "exported", "acknowledged", "rejected", "corrected"]
    currency: str
    debit_minor: int
    credit_minor: int
    checksum: str
    corrects_export_id: UUID | None
    acknowledgement_reference: str | None
    rejection_reason: str | None
    version: int


class ProjectionLineageResponse(BaseModel):
    projection_id: UUID
    period_id: UUID
    confidence: ConfidenceResponse
    completeness_percentage: int
    freshness_status: str
    evidence_lineage: list[UUID]
    integrity_status: Literal["reconciled", "incomplete", "stale", "unknown"]
    version: int
    published_at: datetime


class FinancialIntegrityResponse(BaseModel):
    period_id: UUID
    period_status: Literal["open", "closing", "closed", "reopened"]
    ready_to_close: bool
    integrity_status: Literal["reconciled", "incomplete", "stale", "unknown"]
    blockers: list[str]
    audit_package_digest: str | None
    latest_export_status: str | None
    as_of: datetime
