from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class ProviderPhase(StrEnum):
    QUEUED = "queued"
    COMPOSED = "composed"
    WORKSPACE_READY = "workspace_ready"
    EXECUTING = "executing"
    VALIDATING = "validating"
    COMMIT_READY = "commit_ready"
    PUBLISHING_RESULT = "publishing_result"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RECONCILIATION_REQUIRED = "reconciliation_required"


@dataclass(frozen=True)
class ProviderBoundary:
    allowed_repository: str
    allowed_branch: str
    expected_head: str
    allowed_paths: tuple[str, ...]
    forbidden_paths: tuple[str, ...]
    permitted_operations: tuple[str, ...]
    validation_requirements: tuple[str, ...]


@dataclass(frozen=True)
class ProviderExecutionRequest:
    company_id: UUID
    node_id: UUID
    command_id: UUID
    execution_id: UUID
    lease_id: UUID
    workspace_id: str
    instruction: str
    instruction_digest: str
    request_digest: str
    boundary_digest: str
    boundary: ProviderBoundary
    commit_subject: str
    authority_expires_at: datetime | None = None


@dataclass(frozen=True)
class ProviderExecutionResult:
    execution_id: UUID
    lease_id: UUID
    phase: ProviderPhase
    starting_head: str
    result_head: str | None
    commit_sha: str | None
    files_changed: tuple[str, ...]
    validation: dict[str, bool]
    evidence: dict[str, object]
    reconciliation_reason: str | None = None
