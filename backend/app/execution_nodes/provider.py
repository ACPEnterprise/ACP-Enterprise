import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .boundaries import enforce_changed_paths, validate_request
from .contracts import ProviderExecutionRequest, ProviderExecutionResult, ProviderPhase
from .workspaces import WorkspaceManager


class ProviderFailure(RuntimeError):
    pass


class ProviderJournal:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def append(
        self,
        request: ProviderExecutionRequest,
        phase: ProviderPhase,
        **evidence: object,
    ) -> None:
        target = self.root / f"{request.execution_id}.jsonl"
        payload = {
            "execution_id": str(request.execution_id),
            "lease_id": str(request.lease_id),
            "phase": phase.value,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "evidence": evidence,
        }
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(descriptor, (json.dumps(payload, sort_keys=True) + "\n").encode())
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def latest_phase(self, request: ProviderExecutionRequest) -> ProviderPhase | None:
        target = self.root / f"{request.execution_id}.jsonl"
        if not target.exists():
            return None
        rows = target.read_text(encoding="utf-8").splitlines()
        return ProviderPhase(json.loads(rows[-1])["phase"]) if rows else None

    def latest_evidence(self, request: ProviderExecutionRequest) -> dict[str, object]:
        evidence = self.latest_record(request).get("evidence", {})
        return dict(evidence) if isinstance(evidence, dict) else {}

    def latest_record(self, request: ProviderExecutionRequest) -> dict[str, object]:
        target = self.root / f"{request.execution_id}.jsonl"
        if not target.exists():
            return {}
        rows = target.read_text(encoding="utf-8").splitlines()
        return dict(json.loads(rows[-1])) if rows else {}


class CodexImplementation:
    def __init__(self, executable: Path, auth_root: Path, evidence_root: Path) -> None:
        self.executable = executable.resolve(strict=True)
        self.auth_root = auth_root.resolve(strict=True)
        self.evidence_root = evidence_root.resolve()
        self.evidence_root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def execute(
        self, workspace: Path, request: ProviderExecutionRequest, timeout: int
    ) -> dict[str, object]:
        output = self.evidence_root / f"{request.execution_id}.summary"
        control_root = self.evidence_root / "control" / str(request.execution_id)
        control_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        writable_roots: list[str] = []
        for pattern in request.boundary.allowed_paths:
            prefix = pattern.split("*", 1)[0].rstrip("/")
            target = (workspace / prefix).resolve(strict=True)
            if workspace not in target.parents and target != workspace:
                raise ProviderFailure("Writable boundary escapes the workspace.")
            writable_roots.extend(("--add-dir", str(target)))
        boundary_summary = json.dumps(
            {
                "allowed_paths": request.boundary.allowed_paths,
                "forbidden_paths": request.boundary.forbidden_paths,
                "permitted_operations": request.boundary.permitted_operations,
            },
            sort_keys=True,
        )
        environment = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "CODEX_HOME": str(self.auth_root),
            "HOME": str(self.evidence_root),
            "LANG": "C.UTF-8",
        }
        completed = subprocess.run(
            (
                str(self.executable),
                "exec",
                "--json",
                "--sandbox",
                "workspace-write",
                "--cd",
                str(control_root),
                *writable_roots,
                "--skip-git-repo-check",
                "--output-last-message",
                str(output),
                "--",
                (
                    "You are operating behind the ACP Controlled Execution Provider. "
                    "Do not run git add, git commit, git push, deploy, or modify files "
                    "outside the supplied execution boundary. The provider alone owns "
                    "Git staging, validation, and commit creation.\n\n"
                    "This immutable command and lease prove that the authenticated "
                    "owner already performed the required Start action. Begin the "
                    "bounded implementation now; do not ask for another Start.\n\n"
                    "The operating-system sandbox permits writes only under the "
                    f"following immutable boundary: {boundary_summary}\n\n"
                    f"The enrolled repository root is {workspace}. Perform all "
                    "repository inspection and allowed edits there.\n\n"
                    f"{request.instruction}"
                ),
            ),
            cwd=workspace,
            env=environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if completed.returncode:
            raise ProviderFailure(
                "Codex implementation failed inside its bounded workspace."
            )
        return {
            "implementation": "codex",
            "summary_digest": _file_digest(output),
            "event_count": len(completed.stdout.splitlines()),
        }

    def completed_after(
        self, request: ProviderExecutionRequest, occurred_at: str
    ) -> bool:
        output = self.evidence_root / f"{request.execution_id}.summary"
        if not output.is_file() or not output.read_text(encoding="utf-8").strip():
            return False
        completed_at = datetime.fromtimestamp(output.stat().st_mtime, timezone.utc)
        return completed_at >= datetime.fromisoformat(occurred_at)


class ControlledExecutionProvider:
    def __init__(
        self,
        workspaces: WorkspaceManager,
        journal: ProviderJournal,
        implementation: CodexImplementation,
    ) -> None:
        self.workspaces = workspaces
        self.journal = journal
        self.implementation = implementation

    def execute(
        self, request: ProviderExecutionRequest, *, timeout_seconds: int = 7200
    ) -> ProviderExecutionResult:
        validate_request(request)
        prior = self.journal.latest_phase(request)
        prior_record = self.journal.latest_record(request)
        if prior is ProviderPhase.COMPLETED:
            raise ProviderFailure("Duplicate completed execution is rejected.")
        if (
            prior is ProviderPhase.VALIDATING
            and self.journal.latest_evidence(request).get("files") == []
            and self.workspaces.recovered_workspace_is_pristine(request)
        ):
            self.journal.append(
                request,
                ProviderPhase.QUEUED,
                reason="verified_no_mutation_retry",
            )
            prior = ProviderPhase.QUEUED
        if prior in {
            ProviderPhase.EXECUTING,
            ProviderPhase.COMMIT_READY,
        } and self.workspaces.recovered_workspace_is_pristine(request):
            self.journal.append(
                request,
                ProviderPhase.QUEUED,
                reason="verified_no_mutation_retry",
            )
            prior = ProviderPhase.QUEUED
        resume_after_implementation = (
            prior is ProviderPhase.EXECUTING
            and isinstance(prior_record.get("occurred_at"), str)
            and self.implementation.completed_after(
                request, str(prior_record["occurred_at"])
            )
        )
        resume_at_validation = (
            prior is ProviderPhase.VALIDATING
            and self.workspaces.recovered_workspace_head_is_unchanged(request)
        )
        resume_after_implementation = (
            resume_after_implementation or resume_at_validation
        )
        if (
            prior
            in {
                ProviderPhase.EXECUTING,
                ProviderPhase.VALIDATING,
                ProviderPhase.COMMIT_READY,
                ProviderPhase.PUBLISHING_RESULT,
            }
            and not resume_after_implementation
        ):
            self.journal.append(
                request,
                ProviderPhase.RECONCILIATION_REQUIRED,
                reason="ambiguous_interruption",
            )
            raise ProviderFailure("Interrupted mutation requires reconciliation.")
        with self.workspaces.locked(request):
            if resume_after_implementation:
                workspace = self.workspaces.prepare(request)
                evidence = {
                    "implementation": "codex",
                    "resumed_after_completed_implementation": True,
                }
            else:
                self.journal.append(request, ProviderPhase.COMPOSED)
                workspace = self.workspaces.prepare(request)
                self.journal.append(
                    request,
                    ProviderPhase.WORKSPACE_READY,
                    head=request.boundary.expected_head,
                )
                self.journal.append(request, ProviderPhase.EXECUTING)
                evidence = self.implementation.execute(
                    workspace, request, timeout_seconds
                )
            files = self.workspaces.changed_files(workspace)
            enforce_changed_paths(request.boundary, files)
            self.journal.append(request, ProviderPhase.VALIDATING, files=list(files))
            validations = self._validate(
                workspace, request.boundary.validation_requirements, files
            )
            self.journal.append(
                request,
                ProviderPhase.VALIDATING,
                files=list(files),
                validation=validations,
            )
            if not validations or not all(validations.values()):
                raise ProviderFailure("Required validation failed.")
            self.journal.append(request, ProviderPhase.COMMIT_READY)
            commit = self.workspaces.commit(workspace, request, files)
            self.journal.append(request, ProviderPhase.PUBLISHING_RESULT, commit=commit)
            self.journal.append(request, ProviderPhase.COMPLETED, commit=commit)
            evidence["phases"] = [
                "composed",
                "workspace_ready",
                "executing",
                "validating",
                "commit_ready",
                "publishing_result",
                "completed",
            ]
            return ProviderExecutionResult(
                request.execution_id,
                request.lease_id,
                ProviderPhase.COMPLETED,
                request.boundary.expected_head,
                commit,
                commit,
                files,
                validations,
                evidence,
            )

    @staticmethod
    def _validate(
        workspace: Path, requirements: tuple[str, ...], files: tuple[str, ...]
    ) -> dict[str, bool]:
        python_files = tuple(
            path.removeprefix("backend/")
            for path in files
            if path.startswith("backend/") and path.endswith(".py")
        )
        application_files = tuple(
            path for path in python_files if path.startswith("app/")
        )
        test_files = tuple(path for path in python_files if path.startswith("tests/"))
        component_tests = tuple(
            sorted(
                {
                    f"tests/{path.split('/', 2)[1]}"
                    for path in application_files
                    if len(path.split("/", 2)) >= 2
                    and (
                        workspace / "backend" / f"tests/{path.split('/', 2)[1]}"
                    ).is_dir()
                }
            )
        )
        allowed = {
            "git diff --check": (Path("."), ("git", "diff", "--check", "HEAD")),
            "ruff": (
                Path("backend"),
                (sys.executable, "-m", "ruff", "check", *python_files),
            ),
            "mypy": (
                Path("backend"),
                (sys.executable, "-m", "mypy", *application_files),
            ),
            "pytest": (
                Path("backend"),
                (
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    *(test_files or component_tests),
                ),
            ),
            "eslint": (
                Path("frontend"),
                ("npm", "run", "lint", "--", "--max-warnings=0"),
            ),
            "typescript": (Path("frontend"), ("npm", "run", "build")),
        }
        python_changed = any(path.endswith(".py") for path in files)
        frontend_changed = any(path.startswith("frontend/") for path in files)
        results: dict[str, bool] = {}
        for requirement in requirements:
            normalized = requirement.casefold()
            if normalized in {"ruff", "mypy", "pytest"} and not python_changed:
                results[requirement] = True
                continue
            if normalized == "mypy" and not application_files:
                results[requirement] = True
                continue
            if normalized == "pytest" and not (test_files or component_tests):
                results[requirement] = True
                continue
            if normalized in {"eslint", "typescript"} and not frontend_changed:
                results[requirement] = True
                continue
            validation = allowed.get(normalized)
            if validation is None:
                raise ProviderFailure(f"Validation is not allowlisted: {requirement}")
            relative_cwd, argv = validation
            environment = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "LANG": "C.UTF-8",
                "ENVIRONMENT": "test",
                "PYTHONPATH": str(workspace / "backend"),
            }
            completed = subprocess.run(
                argv,
                cwd=workspace / relative_cwd,
                env=environment,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=1800,
                check=False,
            )
            results[requirement] = completed.returncode == 0
        return results


def _file_digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()
