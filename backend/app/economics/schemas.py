from datetime import datetime
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
    explanation: str


class ProfitMeasurementResponse(BaseModel):
    id: UUID
    company_id: UUID
    branch_id: UUID | None
    subject_type: str
    subject_id: UUID
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
    engine_version: str
    version: int
    measured_at: datetime


class ProfitMeasurementListResponse(BaseModel):
    items: list[ProfitMeasurementResponse]
    limit: int
    offset: int
