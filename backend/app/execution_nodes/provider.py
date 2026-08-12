import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from uuid import UUID

from .boundaries import enforce_changed_paths, validate_request
from .contracts import ProviderExecutionRequest, ProviderExecutionResult, ProviderPhase
from .workspaces import WorkspaceManager, WorkspaceReconciliationRequired


class ProviderFailure(RuntimeError):
    pass


class FrontendValidationEnvironment:
    """Prepare the lockfile-pinned frontend toolchain without network or scripts."""

    def __init__(
        self,
        node_executable: Path,
        npm_executable: Path,
        cache_root: Path,
        *,
        expected_node_version: str,
        expected_npm_version: str,
    ) -> None:
        self.node_executable = node_executable.resolve(strict=True)
        self.npm_executable = npm_executable.resolve(strict=True)
        self.cache_root = cache_root.resolve()
        self.cache_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.cache_root, 0o700)
        self.user_config = self.cache_root / "provider.npmrc"
        if not self.user_config.exists():
            self.user_config.write_text("", encoding="utf-8")
        os.chmod(self.user_config, 0o600)
        self.expected_node_version = expected_node_version.removeprefix("v")
        self.expected_npm_version = expected_npm_version.removeprefix("v")

    def environment(self) -> dict[str, str]:
        path = os.pathsep.join(
            dict.fromkeys(
                (
                    str(self.node_executable.parent),
                    str(self.npm_executable.parent),
                    "/usr/bin",
                    "/bin",
                )
            )
        )
        return {
            "PATH": path,
            "LANG": "C.UTF-8",
            "ENVIRONMENT": "test",
            "NPM_CONFIG_CACHE": str(self.cache_root),
            "NPM_CONFIG_USERCONFIG": str(self.user_config),
            "NPM_CONFIG_OFFLINE": "true",
            "NPM_CONFIG_IGNORE_SCRIPTS": "true",
            "NPM_CONFIG_AUDIT": "false",
            "NPM_CONFIG_FUND": "false",
        }

    def prepare(self, workspace: Path) -> dict[str, object]:
        frontend = workspace / "frontend"
        package = frontend / "package.json"
        lockfile = frontend / "package-lock.json"
        if not package.is_file() or not lockfile.is_file():
            raise ProviderFailure("Frontend validation lockfile is unavailable.")
        environment = self.environment()
        node_version = self._version(self.node_executable, environment)
        npm_version = self._version(self.npm_executable, environment)
        if node_version != self.expected_node_version:
            raise ProviderFailure("Configured Node.js version is not approved.")
        if npm_version != self.expected_npm_version:
            raise ProviderFailure("Configured npm version is not approved.")
        completed = subprocess.run(
            (
                str(self.npm_executable),
                "ci",
                "--ignore-scripts",
                "--offline",
                "--no-audit",
                "--no-fund",
            ),
            cwd=frontend,
            env=environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
        )
        if completed.returncode:
            raise ProviderFailure(
                "Frontend validation dependencies are not available from the "
                "approved offline cache."
            )
        if not (frontend / "node_modules" / ".package-lock.json").is_file():
            raise ProviderFailure("Frontend validation dependencies are incomplete.")
        return {
            "mode": "npm-ci-offline-ignore-scripts",
            "lockfile_sha256": hashlib.sha256(lockfile.read_bytes()).hexdigest(),
            "node_version": node_version,
            "npm_version": npm_version,
        }

    def disposable_environment(self, workspace: Path) -> tuple[dict[str, str], Path]:
        """Return a provider-owned temp environment outside the product boundary."""
        temporary = Path(tempfile.mkdtemp(prefix="validation-", dir=self.cache_root))
        environment = self.environment()
        environment.update(
            {
                "TMPDIR": str(temporary),
                "TMP": str(temporary),
                "TEMP": str(temporary),
            }
        )
        self.clean_generated_artifacts(workspace)
        return environment, temporary

    @staticmethod
    def clean_generated_artifacts(workspace: Path) -> None:
        frontend = (workspace / "frontend").resolve(strict=True)
        for target in (frontend / "node_modules" / ".tmp", frontend / "dist"):
            if target.is_symlink() or target.is_file():
                target.unlink()
            elif target.is_dir():
                shutil.rmtree(target)

    @staticmethod
    def _version(executable: Path, environment: dict[str, str]) -> str:
        completed = subprocess.run(
            (str(executable), "--version"),
            env=environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if completed.returncode or not completed.stdout.strip():
            raise ProviderFailure("Configured frontend toolchain is unavailable.")
        return completed.stdout.strip().removeprefix("v")


def prepare_writable_roots(
    workspace: Path, patterns: tuple[str, ...]
) -> tuple[Path, ...]:
    """Resolve explicit writable roots, including authorized absent directories.

    Boundary patterns are validated before this function is called.  A glob suffix
    describes files below its literal prefix, so creating that missing prefix does
    not widen the boundary to its parent.  Every existing ancestor is resolved
    before creation to prevent a symlink from escaping the enrolled workspace.
    """
    root = workspace.resolve(strict=True)
    roots: list[Path] = []
    for pattern in patterns:
        literal_prefix = pattern.split("*", 1)[0]
        if "*" in pattern and literal_prefix.endswith("/"):
            prefix = literal_prefix.rstrip("/")
        else:
            prefix = str(PurePosixPath(literal_prefix or pattern).parent)
        if not prefix:
            target = root
        else:
            relative = PurePosixPath(prefix)
            if relative.is_absolute() or any(
                part in {"", ".", ".."} for part in relative.parts
            ):
                raise ProviderFailure("Writable boundary path is unsafe.")
            descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            try:
                for part in relative.parts:
                    try:
                        child = os.open(
                            part,
                            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=descriptor,
                        )
                    except FileNotFoundError:
                        os.mkdir(part, mode=0o755, dir_fd=descriptor)
                        child = os.open(
                            part,
                            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=descriptor,
                        )
                    os.close(descriptor)
                    descriptor = child
            except (FileExistsError, NotADirectoryError, OSError) as error:
                raise ProviderFailure(
                    "Writable boundary has an invalid existing ancestor."
                ) from error
            finally:
                os.close(descriptor)
            target = root.joinpath(*relative.parts).resolve(strict=True)
        if target != root and root not in target.parents:
            raise ProviderFailure("Writable boundary escapes the workspace.")
        roots.append(target)
    return tuple(dict.fromkeys(roots))


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
        return self.latest_record_for_execution(request.execution_id)

    def latest_record_for_execution(self, execution_id: UUID) -> dict[str, object]:
        target = self.root / f"{execution_id}.jsonl"
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
        for target in prepare_writable_roots(workspace, request.boundary.allowed_paths):
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
        frontend_validation: FrontendValidationEnvironment | None = None,
    ) -> None:
        self.workspaces = workspaces
        self.journal = journal
        self.implementation = implementation
        self.frontend_validation = frontend_validation

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
                validation_environment = self._prepare_validation_environment(
                    workspace, request.boundary.validation_requirements
                )
                self.journal.append(
                    request,
                    ProviderPhase.WORKSPACE_READY,
                    head=request.boundary.expected_head,
                    validation_environment=validation_environment,
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
            try:
                remote_head, reconciled = self.workspaces.reconcile_for_publish(
                    workspace, request
                )
                if reconciled:
                    files = self.workspaces.committed_files(workspace)
                    enforce_changed_paths(request.boundary, files)
                    validations = self._validate(
                        workspace, request.boundary.validation_requirements, files
                    )
                    if not validations or not all(validations.values()):
                        raise ProviderFailure(
                            "Validation failed after mechanical reconciliation."
                        )
                    commit = self.workspaces._git(workspace, "rev-parse", "HEAD")
                published = self.workspaces.push(workspace, request, remote_head)
            except WorkspaceReconciliationRequired as error:
                self.journal.append(
                    request,
                    ProviderPhase.RECONCILIATION_REQUIRED,
                    reason=str(error),
                )
                raise ProviderFailure(str(error)) from error
            self.journal.append(
                request,
                ProviderPhase.COMPLETED,
                commit=published,
                remote_head_before=remote_head,
                mechanically_reconciled=reconciled,
            )
            evidence.update(
                {
                    "published_commit_sha": published,
                    "remote_head_before": remote_head,
                    "mechanically_reconciled": reconciled,
                }
            )
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
                published,
                published,
                files,
                validations,
                evidence,
            )

    def _validate(
        self, workspace: Path, requirements: tuple[str, ...], files: tuple[str, ...]
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
            "frontend tests": (Path("frontend"), ("npm", "run", "test:run")),
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
            if (
                normalized in {"eslint", "typescript", "frontend tests"}
                and not frontend_changed
            ):
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
            temporary: Path | None = None
            if normalized in {"eslint", "typescript", "frontend tests"}:
                if self.frontend_validation is None:
                    raise ProviderFailure(
                        "Frontend validation environment is not configured."
                    )
                validation_environment, temporary = (
                    self.frontend_validation.disposable_environment(workspace)
                )
                environment.update(validation_environment)
                environment["PYTHONPATH"] = str(workspace / "backend")
            try:
                completed = subprocess.run(
                    argv,
                    cwd=workspace / relative_cwd,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    timeout=1800,
                    check=False,
                )
            finally:
                if self.frontend_validation is not None and temporary is not None:
                    self.frontend_validation.clean_generated_artifacts(workspace)
                    shutil.rmtree(temporary)
            results[requirement] = completed.returncode == 0
        return results

    def _prepare_validation_environment(
        self, workspace: Path, requirements: tuple[str, ...]
    ) -> dict[str, object]:
        frontend_required = any(
            item.casefold() in {"eslint", "typescript", "frontend tests"}
            for item in requirements
        )
        if not frontend_required:
            return {"frontend": "not-required"}
        if self.frontend_validation is None:
            raise ProviderFailure("Frontend validation environment is not configured.")
        return self.frontend_validation.prepare(workspace)


def _file_digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()
