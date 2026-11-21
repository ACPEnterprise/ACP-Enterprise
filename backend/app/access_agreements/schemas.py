from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CurrentAgreementResponse(BaseModel):
    required: bool
    configured: bool
    accepted: bool
    agreement_id: UUID | None = None
    code: str | None = None
    title: str | None = None
    version: int | None = None
    effective_at: datetime | None = None
    content: str | None = None
    content_sha256: str | None = None
    receipt_id: UUID | None = None
    accepted_at: datetime | None = None


class AgreementAcceptRequest(BaseModel):
    agreement_id: UUID
    version: int = Field(ge=1)
    acknowledge_reviewed: bool
    electronic_signature_consent: bool


class AgreementReceiptResponse(BaseModel):
    receipt_id: UUID
    agreement_id: UUID
    agreement_version: int
    agreement_sha256: str
    recipient_name: str
    recipient_email: str
    company_id: UUID
    accepted_at: datetime
    action: str
    electronic_signature_consent: bool
    title: str
    content: str
