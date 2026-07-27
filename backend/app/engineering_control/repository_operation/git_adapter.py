import os
import re
import subprocess
from pathlib import Path, PurePosixPath

from .contracts import CommitRecord, RepositoryState
from .errors import RepositoryOperationGitError

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{10,}", re.IGNORECASE),
    re.compile(r"authorization:\s*bearer\s+\S+", re.IGNORECASE),
    re.compile(r"openai_api_key", re.IGNORECASE),
    re.compile(r"api[_-]?key\s*=", re.IGNORECASE),
)
MAX_OUTPUT = 32_000
GIT_TIMEOUT_SECONDS = 20


class ProductionBoundedGitAdapter:
    """Semantic, local-only Git boundary; no arbitrary command API is exposed."""

    def __init__(self, repository_root: Path) -> None:
        self.root = repository_root.resolve(strict=True)
        if not (self.root / ".git").exists():
            raise RepositoryOperationGitError(
                "repository_unavailable", "Configured repository is unavailable."
            )

    def inspect_repository_state(self) -> RepositoryState:
        changed_files = self._changed_files()
        return RepositoryState(
            branch=self._text(("branch", "--show-current")).strip(),
            head=self._sha(("rev-parse", "HEAD")),
            changed_files=changed_files,
            staged_files=self._names(("diff", "--cached", "--name-only", "-z")),
            ignored_files=self._names(
                (
                    "ls-files",
                    "--others",
                    "--ignored",
                    "--exclude-standard",
                    "-z",
                )
            ),
            missing_files=tuple(
                path for path in changed_files if not (self.root / path).is_file()
            ),
        )

    def stage_exact_files(self, paths: tuple[str, ...]) -> None:
        for path in paths:
            self._validate_path(path)
        attributes = self._git(("check-attr", "-z", "filter", "--", *paths)).stdout
        values = attributes.split("\0")
        if any(value not in {"", "unspecified"} for value in values[2::3]):
            raise RepositoryOperationGitError(
                "external_filter_not_allowed",
                "Authorized files use an unsupported Git filter.",
            )
        self._git(("add", "--", *paths))

    def inspect_staged_state(self) -> RepositoryState:
        return self.inspect_repository_state()

    def validate_staged_content(self) -> None:
        self._git(("diff", "--cached", "--check"))
        patch = self._text(
            ("diff", "--cached", "--no-ext-diff", "--no-color", "--binary")
        )
        if any(pattern.search(patch) for pattern in SECRET_PATTERNS):
            raise RepositoryOperationGitError(
                "secret_pattern_detected",
                "Staged content failed secret-pattern validation.",
            )

    def create_commit(self, subject: str) -> str:
        self._git(("commit", "--no-verify", "--no-gpg-sign", "-m", subject))
        return self.inspect_current_head()

    def inspect_commit(self, sha: str) -> CommitRecord:
        if FULL_SHA.fullmatch(sha) is None:
            raise RepositoryOperationGitError(
                "invalid_commit", "Commit identifier is invalid."
            )
        parent = self._sha(("rev-parse", f"{sha}^"))
        subject = self._text(("show", "-s", "--format=%s", sha)).rstrip("\n")
        files = self._names(
            ("diff-tree", "--no-commit-id", "--name-only", "-r", "-z", sha)
        )
        return CommitRecord(sha=sha, parent=parent, subject=subject, files=files)

    def inspect_current_head(self) -> str:
        return self._sha(("rev-parse", "HEAD"))

    def _changed_files(self) -> tuple[str, ...]:
        tracked = self._names(("diff", "--name-only", "-z", "HEAD"))
        untracked = self._names(("ls-files", "--others", "--exclude-standard", "-z"))
        return tuple(sorted(set(tracked) | set(untracked)))

    def _names(self, arguments: tuple[str, ...]) -> tuple[str, ...]:
        output = self._git(arguments).stdout
        return tuple(sorted(item for item in output.split("\0") if item))

    def _sha(self, arguments: tuple[str, ...]) -> str:
        value = self._text(arguments).strip()
        if FULL_SHA.fullmatch(value) is None:
            raise RepositoryOperationGitError(
                "invalid_repository_state", "Repository returned an invalid commit."
            )
        return value

    def _text(self, arguments: tuple[str, ...]) -> str:
        return self._git(arguments).stdout

    def _git(self, arguments: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", ""),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        try:
            result = subprocess.run(
                (
                    "git",
                    "-c",
                    "core.hooksPath=/dev/null",
                    "-c",
                    "core.fsmonitor=false",
                    *arguments,
                ),
                cwd=self.root,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=GIT_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            classification = (
                "git_timeout"
                if isinstance(error, subprocess.TimeoutExpired)
                else "git_unavailable"
            )
            raise RepositoryOperationGitError(
                classification, "Bounded Git operation did not complete."
            ) from error
        if len(result.stdout) > MAX_OUTPUT or len(result.stderr) > MAX_OUTPUT:
            raise RepositoryOperationGitError(
                "git_output_too_large", "Bounded Git output exceeded its limit."
            )
        if result.returncode != 0:
            raise RepositoryOperationGitError(
                "git_command_failed", "Bounded Git operation failed."
            )
        return result

    def _validate_path(self, path: str) -> None:
        parsed = PurePosixPath(path)
        if (
            not path
            or parsed.is_absolute()
            or ".." in parsed.parts
            or ".git" in parsed.parts
            or "\\" in path
        ):
            raise RepositoryOperationGitError(
                "invalid_file_boundary", "Authorized file path is invalid."
            )
        resolved = (self.root / path).resolve(strict=False)
        if not resolved.is_relative_to(self.root):
            raise RepositoryOperationGitError(
                "path_escape", "Authorized file path escapes the repository."
            )
        if not resolved.is_file():
            raise RepositoryOperationGitError(
                "authorized_file_missing", "An authorized file is missing."
            )
        current = self.root
        for part in parsed.parts[:-1]:
            current = current / part
            if current.is_symlink() and not current.resolve().is_relative_to(self.root):
                raise RepositoryOperationGitError(
                    "symlink_escape", "Authorized path crosses an external symlink."
                )
