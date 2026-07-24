from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.engineering_control.records import (
    EngineeringApprovalState,
    EngineeringCommandRecord,
)


@dataclass(frozen=True)
class CreateEngineeringCommand:
    command_type: str
    owner_instruction: str
    repository_key: str
    expected_branch: str
    expected_head: str
    requested_code_changes: bool
    expires_at: datetime
    idempotency_key: str
    correlation_id: UUID | None = None


@dataclass(frozen=True)
class ApproveEngineeringCommand:
    command_id: UUID
    expected_version: int
    instruction_digest: str
    request_digest: str
    repository_key: str
    expected_branch: str
    expected_head: str
    requested_code_changes: bool


@dataclass(frozen=True)
class CancelEngineeringCommand:
    command_id: UUID
    expected_version: int
    reason_code: str


@dataclass(frozen=True)
class ExpireEngineeringCommand:
    command_id: UUID
    expected_version: int


@dataclass(frozen=True)
class EngineeringCommandQuery:
    approval_state: EngineeringApprovalState | None = None
    page: int = 1
    page_size: int = 50


@dataclass(frozen=True)
class EngineeringCommandPage:
    items: tuple[EngineeringCommandRecord, ...]
    page: int
    page_size: int
    total_count: int
    total_pages: int
