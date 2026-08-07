from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    action: str
    outcome: str
    actor_user_id: UUID | None
    company_id: UUID
    branch_id: UUID | None
    resource_type: str
    resource_id: UUID | None
    reason_code: str | None
    correlation_id: UUID
    details: dict[str, object]
    occurred_at: datetime
