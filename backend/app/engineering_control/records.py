from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4


class EngineeringApprovalState(StrEnum):
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELED = "canceled"
    EXPIRED = "expired"


class EngineeringExecutionState(StrEnum):
    EXECUTION_NOT_CONNECTED = "execution_not_connected"


class EngineeringMutationStatus(StrEnum):
    APPLIED = "applied"
    NOT_FOUND = "not_found"
    STALE_VERSION = "stale_version"
    INELIGIBLE_STATE = "ineligible_state"


@dataclass(frozen=True)
class CreateEngineeringCommand:
    company_id: UUID
    requested_by_user_id: UUID
    command_type: str
    owner_instruction: str
    instruction_digest: str
    repository_key: str
    expected_branch: str
    expected_head: str
    requested_code_changes: bool
    idempotency_key: str
    request_digest: str
    expires_at: datetime
    created_at: datetime
    correlation_id: UUID = field(default_factory=uuid4)


@dataclass(frozen=True)
class EngineeringCommandRecord:
    id: UUID
    ecid: str
    company_id: UUID
    requested_by_user_id: UUID
    command_type: str
    owner_instruction: str
    instruction_digest: str
    repository_key: str
    expected_branch: str
    expected_head: str
    requested_code_changes: bool
    approval_state: EngineeringApprovalState
    execution_state: EngineeringExecutionState
    idempotency_key: str
    request_digest: str
    correlation_id: UUID
    failure_code: str | None
    cancellation_reason_code: str | None
    expires_at: datetime
    version: int
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None
    approved_by_user_id: UUID | None
    canceled_at: datetime | None
    canceled_by_user_id: UUID | None
    result_reference: str | None


@dataclass(frozen=True)
class EngineeringCommandMutationResult:
    status: EngineeringMutationStatus
    record: EngineeringCommandRecord | None = None


@dataclass(frozen=True)
class EngineeringCommandQueryResult:
    items: tuple[EngineeringCommandRecord, ...]
    total_count: int


@dataclass(frozen=True)
class AppendEngineeringCommandEvent:
    company_id: UUID
    command_id: UUID
    ecid: str
    instruction_digest: str
    event_type: str
    occurred_at: datetime
    correlation_id: UUID
    prior_approval_state: EngineeringApprovalState | None = None
    new_approval_state: EngineeringApprovalState | None = None
    prior_execution_state: EngineeringExecutionState | None = None
    new_execution_state: EngineeringExecutionState | None = None
    actor_user_id: UUID | None = None
    reason_code: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class EngineeringCommandEventRecord:
    id: UUID
    company_id: UUID
    command_id: UUID
    ecid: str
    instruction_digest: str
    sequence_number: int
    event_type: str
    prior_approval_state: EngineeringApprovalState | None
    new_approval_state: EngineeringApprovalState | None
    prior_execution_state: EngineeringExecutionState | None
    new_execution_state: EngineeringExecutionState | None
    actor_user_id: UUID | None
    reason_code: str | None
    metadata: Mapping[str, object]
    correlation_id: UUID
    occurred_at: datetime
    created_at: datetime
