from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class RepositoryOperationType(StrEnum):
    CREATE_COMMIT = "create_commit"


class RepositoryOperationState(StrEnum):
    REQUESTED = "requested"
    RESERVED = "reserved"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RECONCILIATION_REQUIRED = "reconciliation_required"


class RepositoryOperationEventType(StrEnum):
    REQUESTED = "requested"
    RESERVED = "reserved"
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RECONCILIATION_REQUIRED = "reconciliation_required"


@dataclass(frozen=True)
class RepositoryState:
    branch: str
    head: str
    changed_files: tuple[str, ...]
    staged_files: tuple[str, ...]
    ignored_files: tuple[str, ...]
    missing_files: tuple[str, ...]


@dataclass(frozen=True)
class CommitRecord:
    sha: str
    parent: str
    subject: str
    files: tuple[str, ...]


class BoundedGitAdapter(Protocol):
    def inspect_repository_state(self) -> RepositoryState: ...

    def stage_exact_files(self, paths: tuple[str, ...]) -> None: ...

    def inspect_staged_state(self) -> RepositoryState: ...

    def validate_staged_content(self) -> None: ...

    def create_commit(self, subject: str) -> str: ...

    def inspect_commit(self, sha: str) -> CommitRecord: ...

    def inspect_current_head(self) -> str: ...


@dataclass(frozen=True)
class RepositoryOperationReadiness:
    eligible: bool
    reason_code: str | None
    inspected_at: datetime
