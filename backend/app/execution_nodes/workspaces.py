import fcntl
import re
import shutil
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .contracts import ProviderExecutionRequest


class WorkspaceFailure(RuntimeError):
    pass


class WorkspaceReconciliationRequired(WorkspaceFailure):
    pass


class WorkspaceManager:
    def __init__(self, root: Path, repositories: dict[str, Path]) -> None:
        self.root = root.resolve()
        self.repositories = {
            key: value.resolve(strict=True) for key, value in repositories.items()
        }
        (self.root / "executions").mkdir(parents=True, exist_ok=True, mode=0o700)
        (self.root / "locks").mkdir(parents=True, exist_ok=True, mode=0o700)

    @contextmanager
    def locked(self, request: ProviderExecutionRequest) -> Iterator[None]:
        # A repository-wide lock conservatively prevents overlapping paths across
        # branches. Future providers may replace this with a proven disjoint-path
        # lock without weakening the current collision guarantee.
        key = re.sub(r"[^a-zA-Z0-9_.-]", "_", request.boundary.allowed_repository)
        handle = (self.root / "locks" / f"{key}.lock").open("a+")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            handle.close()
            raise WorkspaceFailure("Repository branch is already executing.") from error
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()

    def prepare(self, request: ProviderExecutionRequest) -> Path:
        repository = self.repositories.get(request.boundary.allowed_repository)
        if repository is None:
            raise WorkspaceFailure("Repository is not enrolled on this node.")
        if self._git(repository, "status", "--porcelain=v1"):
            raise WorkspaceFailure("Enrolled repository is dirty.")
        if (
            self._git(
                repository, "rev-parse", "--verify", request.boundary.expected_head
            )
            != request.boundary.expected_head
        ):
            raise WorkspaceFailure("Expected HEAD is unavailable.")
        if (
            self._git(
                repository,
                "rev-parse",
                "--verify",
                f"refs/heads/{request.boundary.allowed_branch}",
            )
            != request.boundary.expected_head
        ):
            raise WorkspaceFailure("Approved branch no longer matches expected HEAD.")
        target = (
            self.root / "executions" / str(request.company_id) / request.workspace_id
        )
        if target.exists():
            if (
                self._git(
                    target, "rev-list", "--max-count=1", request.boundary.expected_head
                )
                != request.boundary.expected_head
            ):
                raise WorkspaceFailure("Recovered workspace identity is ambiguous.")
            return target
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        branch = f"provider/{request.execution_id}"
        self._git(
            repository,
            "worktree",
            "add",
            "--detach",
            str(target),
            request.boundary.expected_head,
        )
        try:
            self._git(target, "switch", "-c", branch)
        except BaseException:
            shutil.rmtree(target, ignore_errors=True)
            raise
        return target

    def recovered_workspace_is_pristine(
        self, request: ProviderExecutionRequest
    ) -> bool:
        target = (
            self.root / "executions" / str(request.company_id) / request.workspace_id
        )
        return (
            target.is_dir()
            and self._git(target, "rev-parse", "HEAD") == request.boundary.expected_head
            and not self.changed_files(target)
        )

    def recovered_workspace_head_is_unchanged(
        self, request: ProviderExecutionRequest
    ) -> bool:
        target = (
            self.root / "executions" / str(request.company_id) / request.workspace_id
        )
        return (
            target.is_dir()
            and self._git(target, "rev-parse", "HEAD") == request.boundary.expected_head
        )

    @staticmethod
    def changed_files(workspace: Path) -> tuple[str, ...]:
        completed = subprocess.run(
            ("git", "status", "--porcelain=v1", "--untracked-files=all", "-z"),
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if completed.returncode:
            raise WorkspaceFailure((completed.stderr or completed.stdout)[:800])
        raw = completed.stdout
        return tuple(
            sorted({item[3:].split(" -> ")[-1] for item in raw.split("\0") if item})
        )

    @staticmethod
    def committed_files(workspace: Path) -> tuple[str, ...]:
        return tuple(
            sorted(
                filter(
                    None,
                    WorkspaceManager._git(
                        workspace, "diff", "--name-only", "HEAD^", "HEAD"
                    ).splitlines(),
                )
            )
        )

    @staticmethod
    def commit(
        workspace: Path, request: ProviderExecutionRequest, files: tuple[str, ...]
    ) -> str:
        if (
            WorkspaceManager._git(workspace, "rev-parse", "HEAD")
            != request.boundary.expected_head
        ):
            raise WorkspaceFailure("Workspace HEAD changed before commit.")
        if not files:
            raise WorkspaceFailure("Execution produced no repository changes.")
        WorkspaceManager._git(workspace, "add", "--all", "--", *files)
        WorkspaceManager._git(
            workspace,
            "-c",
            "user.name=ACP Execution Provider",
            "-c",
            "user.email=provider@acp.invalid",
            "commit",
            "--no-gpg-sign",
            "-m",
            request.commit_subject,
        )
        return WorkspaceManager._git(workspace, "rev-parse", "HEAD")

    @staticmethod
    def reconcile_for_publish(
        workspace: Path, request: ProviderExecutionRequest
    ) -> tuple[str, bool]:
        """Fetch and perform only a provably mechanical, disjoint rebase."""
        WorkspaceManager._git(
            workspace, "fetch", "--no-tags", "origin", request.boundary.allowed_branch
        )
        remote_head = WorkspaceManager._git(workspace, "rev-parse", "FETCH_HEAD")
        if remote_head == request.boundary.expected_head:
            return remote_head, False
        merge_base = WorkspaceManager._git(
            workspace, "merge-base", request.boundary.expected_head, remote_head
        )
        if merge_base != request.boundary.expected_head:
            raise WorkspaceReconciliationRequired(
                "Authoritative branch is not a descendant of the approved starting head."
            )
        local_files = set(
            WorkspaceManager._git(
                workspace,
                "diff",
                "--name-only",
                request.boundary.expected_head,
                "HEAD",
            ).splitlines()
        )
        remote_files = set(
            WorkspaceManager._git(
                workspace,
                "diff",
                "--name-only",
                request.boundary.expected_head,
                remote_head,
            ).splitlines()
        )
        migration_prefix = "backend/alembic/versions/"
        serialized_prefixes = (
            "backend/app/auth",
            "backend/app/platform",
            "backend/app/events",
            "backend/app/engineering_control",
            "backend/app/engineering_execution",
            "backend/app/worker_",
            ".github/",
        )
        all_files = local_files | remote_files
        if (
            local_files & remote_files
            or any(path.startswith(migration_prefix) for path in all_files)
            or any(path.startswith(serialized_prefixes) for path in all_files)
        ):
            raise WorkspaceReconciliationRequired(
                "Authoritative changes require serialized owner-reviewed reconciliation."
            )
        WorkspaceManager._git(workspace, "rebase", remote_head)
        return remote_head, True

    @staticmethod
    def push(
        workspace: Path, request: ProviderExecutionRequest, remote_head: str
    ) -> str:
        current = WorkspaceManager._git(workspace, "rev-parse", "HEAD")
        try:
            WorkspaceManager._git(
                workspace,
                "push",
                "origin",
                f"{current}:refs/heads/{request.boundary.allowed_branch}",
            )
        except WorkspaceFailure as error:
            raise WorkspaceReconciliationRequired(
                "Normal push was rejected; authoritative state must be reconciled."
            ) from error
        published = WorkspaceManager._git(
            workspace,
            "ls-remote",
            "--heads",
            "origin",
            f"refs/heads/{request.boundary.allowed_branch}",
        ).split()[0]
        if published != current:
            raise WorkspaceReconciliationRequired(
                "Published branch did not resolve to the controlled commit."
            )
        return published

    @staticmethod
    def _git(cwd: Path, *argv: str) -> str:
        completed = subprocess.run(
            ("git", *argv),
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if completed.returncode:
            raise WorkspaceFailure((completed.stderr or completed.stdout).strip()[:800])
        return completed.stdout.strip()
