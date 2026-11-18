from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class MigrationSupportCaseCreate(BaseModel):
    onboarding_stage: str = Field(min_length=1, max_length=40)
    source: str | None = Field(default=None, max_length=80)
    domain: str | None = Field(default=None, max_length=80)
    message: str = Field(min_length=1, max_length=4000)


class MigrationSupportCaseView(BaseModel):
    id: UUID
    company_id: UUID
    onboarding_stage: str
    source: str | None
    domain: str | None
    status: str
    created_at: datetime
