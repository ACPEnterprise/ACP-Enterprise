from __future__ import annotations

import subprocess
from collections import Counter
from pathlib import Path

from development_factory.models import ClassifiedFile, RepositoryState


def inspect_repository(repo_root: Path) -> RepositoryState:
    branch = _git(repo_root, "branch", "--show-current").strip()
    head = _git(repo_root, "rev-parse", "HEAD").strip()
    porcelain = _git(
        repo_root, "status", "--porcelain=v1", "-z", "--untracked-files=all"
    )
    conflicts = [
        line
        for line in _git(
            repo_root, "diff", "--name-only", "--diff-filter=U"
        ).splitlines()
        if line
    ]
    files: list[ClassifiedFile] = []
    entries = [entry for entry in porcelain.split("\0") if entry]
    index = 0
    while index < len(entries):
        entry = entries[index]
        state, path = entry[:2], entry[3:]
        if state[0] in {"R", "C"} and index + 1 < len(entries):
            index += 1
            path = entries[index]
        files.append(
            ClassifiedFile(
                path=path,
                state=state,
                category=classify_path(path),
                staged=state[0] not in {" ", "?"},
                untracked=state == "??",
            )
        )
        index += 1
    return RepositoryState(branch=branch, head=head, files=files, conflicts=conflicts)


def classify_path(path: str) -> str:
    if path == ".gitignore":
        return "development_tooling"
    if path.startswith("backend/alembic/versions/"):
        return "migrations"
    if path.startswith("backend/tests/"):
        return "backend_tests"
    if path.startswith("backend/app/"):
        return "backend_runtime"
    if path.startswith("frontend/src/") and (
        path.endswith(".test.ts") or path.endswith(".test.tsx")
    ):
        return "frontend_tests"
    if path.startswith("frontend/"):
        return "frontend_runtime"
    if path.startswith("docs/") or path.endswith(".md"):
        return "documentation"
    if path.startswith(("infrastructure/", "docker/")) or "deploy" in path:
        return "infrastructure"
    if path.startswith(
        ("development-factory/", "backend/development_factory/", "scripts/")
    ):
        return "development_tooling"
    return "unknown"


def classification_summary(state: RepositoryState) -> dict[str, int]:
    return dict(sorted(Counter(item.category for item in state.files).items()))


def sensitive_change_flags(state: RepositoryState) -> dict[str, bool]:
    paths = [item.path.lower() for item in state.files]
    return {
        "migration_changed": any("alembic/versions/" in path for path in paths),
        "authorization_sensitive_changed": any(
            token in path
            for path in paths
            for token in ("auth", "permission", "security")
        ),
        "tenant_persistence_changed": any(
            path.endswith("models.py") or "repository" in path for path in paths
        ),
        "infrastructure_changed": any(
            item.category == "infrastructure" for item in state.files
        ),
        "mixed_runtime_domains": len(
            {
                path.split("/")[2]
                for path in paths
                if path.startswith("backend/app/") and len(path.split("/")) > 2
            }
        )
        > 1,
    }


def _git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", *args),
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout
