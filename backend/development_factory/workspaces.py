from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from development_factory.lia_contract import (
    LiaSupervisoryContract,
    WorkerAssignment,
    load_lia_contract,
)
from development_factory.lia_roles import load_agent_roles
from development_factory.repository import inspect_repository
from development_factory.reports import redact


WORKSPACE_METADATA_VERSION = "1.0"
WorkspaceClassification = Literal[
    "planned",
    "ready",
    "dirty",
    "staged",
    "untracked",
    "stale",
    "interrupted",
    "orphaned_metadata",
    "metadata_mismatch",
    "duplicate_ownership",
    "repository_diverged",
]


class WorkspaceError(ValueError):
    pass


@dataclass(frozen=True)
class WorkspaceIdentity:
    workspace_id: str
    worker_id: str
    task_id: str
    supervisory_run_id: str
    approved_branch: str
    approved_starting_sha: str
    workspace_path: str
    workspace_branch: str


@dataclass(frozen=True)
class WorkspaceMetadata:
    schema_version: str
    identity: WorkspaceIdentity
    created_at: str
    inspected_at: str
    repository_state: str
    validation_status: str

    def to_dict(self) -> dict[str, Any]:
        return _sanitize(asdict(self))


@dataclass(frozen=True)
class WorkspaceInspection:
    identity: WorkspaceIdentity
    classification: WorkspaceClassification
    issues: tuple[str, ...]
    metadata_present: bool
    workspace_present: bool
    branch: str | None = None
    head: str | None = None
    dirty: bool = False
    staged_files: tuple[str, ...] = ()
    untracked_files: tuple[str, ...] = ()

    @property
    def requires_owner_review(self) -> bool:
        return self.classification not in {"planned", "ready"}


class WorkspaceManager:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.roles_path = self.repo_root / "development-factory" / "agent-roles.json"
        self.artifact_root = self.repo_root / ".development-factory"

    def load(
        self, contract_path: Path, workspace_id: str
    ) -> tuple[LiaSupervisoryContract, WorkerAssignment, WorkspaceIdentity]:
        roles = load_agent_roles(self.roles_path)
        contract = load_lia_contract(self._resolve(contract_path), roles)
        matches = [
            worker
            for worker in contract.workers
            if worker.workspace.workspace_id == workspace_id
        ]
        if len(matches) != 1:
            raise WorkspaceError(
                f"workspace_id must identify exactly one worker: {workspace_id}"
            )
        worker = matches[0]
        return contract, worker, self.identity(contract, worker)

    def identity(
        self, contract: LiaSupervisoryContract, worker: WorkerAssignment
    ) -> WorkspaceIdentity:
        run_segment = _stable_segment(contract.supervisory_run_id)
        workspace_segment = _stable_segment(worker.workspace.workspace_id)
        workspace_path = (
            self.artifact_root / "workspaces" / run_segment / workspace_segment
        ).resolve()
        expected_root = (self.artifact_root / "workspaces").resolve()
        if expected_root not in workspace_path.parents:
            raise WorkspaceError("derived workspace path escaped its artifact root")
        branch = (
            f"lia/{run_segment}/{workspace_segment}-"
            f"{contract.expected_starting_head[:12]}"
        )
        return WorkspaceIdentity(
            workspace_id=worker.workspace.workspace_id,
            worker_id=worker.agent_id,
            task_id=worker.task.task_id,
            supervisory_run_id=contract.supervisory_run_id,
            approved_branch=contract.expected_branch,
            approved_starting_sha=contract.expected_starting_head,
            workspace_path=str(workspace_path),
            workspace_branch=branch,
        )

    def inspect(self, contract_path: Path, workspace_id: str) -> WorkspaceInspection:
        contract, _, identity = self.load(contract_path, workspace_id)
        return self._inspect(contract, identity)

    def list(self, contract_path: Path) -> tuple[WorkspaceInspection, ...]:
        roles = load_agent_roles(self.roles_path)
        contract = load_lia_contract(self._resolve(contract_path), roles)
        return tuple(
            self._inspect(contract, self.identity(contract, worker))
            for worker in sorted(
                contract.workers, key=lambda item: item.workspace.workspace_id
            )
        )

    def prepare(
        self, contract_path: Path, workspace_id: str
    ) -> tuple[WorkspaceMetadata, bool]:
        contract, _, identity = self.load(contract_path, workspace_id)
        primary_issues = self._primary_repository_issues(contract)
        if primary_issues:
            raise WorkspaceError("; ".join(primary_issues))
        inspection = self._inspect(contract, identity)
        if inspection.classification == "ready":
            metadata = self._read_metadata(identity)
            refreshed = WorkspaceMetadata(
                schema_version=metadata.schema_version,
                identity=metadata.identity,
                created_at=metadata.created_at,
                inspected_at=_timestamp(),
                repository_state="ready",
                validation_status=metadata.validation_status,
            )
            self._write_metadata(refreshed)
            return refreshed, True
        if inspection.classification != "planned":
            raise WorkspaceError(
                f"workspace requires owner review ({inspection.classification}): "
                + "; ".join(inspection.issues)
            )

        workspace_path = Path(identity.workspace_path)
        workspace_path.parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            (
                "git",
                "worktree",
                "add",
                "-b",
                identity.workspace_branch,
                str(workspace_path),
                identity.approved_starting_sha,
            ),
            cwd=self.repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise WorkspaceError(f"Git workspace preparation failed: {redact(detail)}")

        now = _timestamp()
        metadata = WorkspaceMetadata(
            schema_version=WORKSPACE_METADATA_VERSION,
            identity=identity,
            created_at=now,
            inspected_at=now,
            repository_state="ready",
            validation_status="not_run",
        )
        self._write_metadata(metadata)
        verification = self._inspect(contract, identity)
        if verification.classification != "ready":
            raise WorkspaceError(
                "prepared workspace could not be verified; owner review required: "
                + "; ".join(verification.issues)
            )
        return metadata, False

    def show(self, contract_path: Path, workspace_id: str) -> WorkspaceMetadata:
        _, _, identity = self.load(contract_path, workspace_id)
        return self._read_metadata(identity)

    def read_metadata(self, identity: WorkspaceIdentity) -> WorkspaceMetadata:
        return self._read_metadata(identity)

    def primary_repository_issues(
        self, contract: LiaSupervisoryContract
    ) -> tuple[str, ...]:
        return self._primary_repository_issues(contract)

    def _inspect(
        self,
        contract: LiaSupervisoryContract,
        identity: WorkspaceIdentity,
    ) -> WorkspaceInspection:
        primary_issues = self._primary_repository_issues(contract)
        path = Path(identity.workspace_path)
        metadata_path = self._metadata_path(identity)
        path_present = path.exists()
        metadata_present = metadata_path.exists()
        ownership_issues = self._ownership_issues(identity)

        if primary_issues:
            return WorkspaceInspection(
                identity,
                "repository_diverged",
                primary_issues,
                metadata_present,
                path_present,
            )
        if ownership_issues:
            return WorkspaceInspection(
                identity,
                "duplicate_ownership",
                ownership_issues,
                metadata_present,
                path_present,
            )
        if not path_present and not metadata_present:
            return WorkspaceInspection(identity, "planned", (), False, False)
        if path_present and not metadata_present:
            return WorkspaceInspection(
                identity,
                "interrupted",
                ("workspace exists without authoritative metadata",),
                False,
                True,
            )
        if metadata_present and not path_present:
            return WorkspaceInspection(
                identity,
                "orphaned_metadata",
                ("workspace metadata exists but workspace path is absent",),
                True,
                False,
            )
        try:
            metadata = self._read_metadata(identity)
        except WorkspaceError as exc:
            return WorkspaceInspection(
                identity, "metadata_mismatch", (str(exc),), True, True
            )
        if metadata.identity != identity:
            return WorkspaceInspection(
                identity,
                "metadata_mismatch",
                ("workspace metadata identity does not match the contract",),
                True,
                True,
            )

        branch = _git(path, "branch", "--show-current").strip()
        head = _git(path, "rev-parse", "HEAD").strip()
        porcelain = _git(
            path, "status", "--porcelain=v1", "-z", "--untracked-files=all"
        )
        entries = tuple(item for item in porcelain.split("\0") if item)
        staged = tuple(
            sorted(item[3:] for item in entries if item[0] not in {" ", "?"})
        )
        untracked = tuple(sorted(item[3:] for item in entries if item[:2] == "??"))
        dirty = bool(entries)
        issues: tuple[str, ...]
        if not branch:
            issues = ("workspace is unexpectedly detached",)
            classification: WorkspaceClassification = "stale"
        elif branch != identity.workspace_branch:
            issues = (
                f"workspace branch mismatch: expected {identity.workspace_branch}, "
                f"found {branch}",
            )
            classification = "stale"
        elif head != identity.approved_starting_sha:
            issues = (
                f"workspace HEAD drift: expected {identity.approved_starting_sha}, "
                f"found {head}",
            )
            classification = "stale"
        elif staged:
            issues = ("workspace contains staged files",)
            classification = "staged"
        elif untracked:
            issues = ("workspace contains untracked files",)
            classification = "untracked"
        elif dirty:
            issues = ("workspace contains unstaged changes",)
            classification = "dirty"
        else:
            issues = ()
            classification = "ready"
        return WorkspaceInspection(
            identity,
            classification,
            issues,
            True,
            True,
            branch,
            head,
            dirty,
            staged,
            untracked,
        )

    def _primary_repository_issues(
        self, contract: LiaSupervisoryContract
    ) -> tuple[str, ...]:
        state = inspect_repository(self.repo_root)
        issues: list[str] = []
        if state.branch != contract.expected_branch:
            issues.append(
                f"owner branch mismatch: expected {contract.expected_branch}, "
                f"found {state.branch}"
            )
        if state.head != contract.expected_starting_head:
            issues.append(
                f"owner HEAD mismatch: expected {contract.expected_starting_head}, "
                f"found {state.head}"
            )
        if not state.working_tree_clean:
            issues.append("owner working tree must be clean")
        if not state.index_clean:
            issues.append("owner Git index must be empty")
        return tuple(issues)

    def _ownership_issues(self, identity: WorkspaceIdentity) -> tuple[str, ...]:
        metadata_root = self.artifact_root / "workspace-metadata"
        if not metadata_root.exists():
            return ()
        matches: list[str] = []
        for path in sorted(metadata_root.glob("*.json")):
            if path == self._metadata_path(identity):
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                candidate = payload.get("identity", {})
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(candidate, dict):
                continue
            if (
                candidate.get("workspace_id") == identity.workspace_id
                or candidate.get("workspace_path") == identity.workspace_path
                or candidate.get("workspace_branch") == identity.workspace_branch
            ):
                matches.append(path.name)
        if not matches:
            return ()
        return (
            "workspace identity is already owned by metadata: "
            + ", ".join(sorted(matches)),
        )

    def _metadata_path(self, identity: WorkspaceIdentity) -> Path:
        key = hashlib.sha256(
            f"{identity.supervisory_run_id}:{identity.workspace_id}".encode()
        ).hexdigest()[:16]
        return self.artifact_root / "workspace-metadata" / f"{key}.json"

    def _read_metadata(self, identity: WorkspaceIdentity) -> WorkspaceMetadata:
        path = self._metadata_path(identity)
        try:
            payload: Any = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkspaceError(f"unable to read workspace metadata: {exc}") from exc
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != WORKSPACE_METADATA_VERSION
        ):
            raise WorkspaceError("workspace metadata version is invalid")
        raw_identity = payload.get("identity")
        if not isinstance(raw_identity, dict):
            raise WorkspaceError("workspace metadata identity is invalid")
        try:
            return WorkspaceMetadata(
                schema_version=payload["schema_version"],
                identity=WorkspaceIdentity(**raw_identity),
                created_at=str(payload["created_at"]),
                inspected_at=str(payload["inspected_at"]),
                repository_state=str(payload["repository_state"]),
                validation_status=str(payload["validation_status"]),
            )
        except (KeyError, TypeError) as exc:
            raise WorkspaceError("workspace metadata is incomplete") from exc

    def _write_metadata(self, metadata: WorkspaceMetadata) -> None:
        path = self._metadata_path(metadata.identity)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(metadata.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _resolve(self, path: Path) -> Path:
        return path if path.is_absolute() else self.repo_root / path


def _stable_segment(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "workspace"
    digest = hashlib.sha256(value.encode()).hexdigest()[:8]
    return f"{normalized[:40]}-{digest}"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", *args),
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise WorkspaceError(f"Git inspection failed: {redact(detail)}")
    return completed.stdout


def _sanitize(value: Any) -> Any:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    return value
