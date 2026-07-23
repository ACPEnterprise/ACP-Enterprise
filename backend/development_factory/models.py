from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal


CheckStatus = Literal[
    "passed", "failed", "skipped", "unavailable", "blocked", "not_applicable"
]
FindingSeverity = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class CheckDefinition:
    id: str
    name: str
    category: str
    required: bool
    areas: tuple[str, ...]
    timeout_seconds: int
    dependencies: tuple[str, ...]
    failure_classification: str
    parallel: bool
    order: int
    command: tuple[str, ...] | None = None
    implementation: str | None = None
    working_directory: str | None = None


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: FindingSeverity
    message: str
    path: str
    line: int | None = None
    suppressed: bool = False
    rationale: str | None = None


@dataclass(frozen=True)
class CheckResult:
    id: str
    name: str
    category: str
    required: bool
    status: CheckStatus
    duration_seconds: float
    summary: str
    failure_classification: str | None = None
    output: str = ""
    findings: tuple[Finding, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ClassifiedFile:
    path: str
    state: str
    category: str
    staged: bool
    untracked: bool


@dataclass
class RepositoryState:
    branch: str
    head: str
    files: list[ClassifiedFile] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    @property
    def working_tree_clean(self) -> bool:
        return not self.files

    @property
    def index_clean(self) -> bool:
        return not any(item.staged for item in self.files)
