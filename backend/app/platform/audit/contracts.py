from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AuditQuery:
    company_id: UUID
    authorized_branch_ids: frozenset[UUID]
    has_all_branch_access: bool
    branch_id: UUID | None = None
    limit: int = 50


@dataclass(frozen=True, slots=True)
class AuditRecordView:
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
