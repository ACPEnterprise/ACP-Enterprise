from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.events.types import EventType


class BusinessEventCreate(BaseModel):
    event_type: EventType
    entity_type: str = Field(min_length=1, max_length=100)
    entity_id: UUID | None = None

    company_id: UUID | None = None
    branch_id: UUID | None = None
    user_id: UUID | None = None

    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: UUID | None = None
    occurred_at: datetime | None = None


class BusinessEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_type: EventType
    entity_type: str
    entity_id: UUID | None

    company_id: UUID | None
    branch_id: UUID | None
    user_id: UUID | None

    payload: dict[str, Any]
    correlation_id: UUID
    occurred_at: datetime
    created_at: datetime
