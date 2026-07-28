from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ControlledSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PrepareControlledOfferRequest(ControlledSchema):
    workspace_id: str = Field(min_length=3, max_length=100)
    lease_seconds: int = Field(default=300, ge=30, le=900)


class ControlledOfferResponse(ControlledSchema):
    id: UUID
    command_id: UUID
    execution_id: UUID
    workspace_id: str
    command_type: str
    capability_required: str
    state: str
    expires_at: datetime
    lease_seconds: int
    created_at: datetime
