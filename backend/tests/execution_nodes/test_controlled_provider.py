import hashlib
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from app.execution_nodes.boundaries import BoundaryViolation, boundary_digest
from app.execution_nodes.contracts import (
    ProviderBoundary,
    ProviderExecutionRequest,
    ProviderPhase,
)
from app.execution_nodes.provider import (
    ControlledExecutionProvider,
    ProviderFailure,
    ProviderJournal,
)
from app.execution_nodes.workspaces import WorkspaceManager


class Implementation:
    def execute(
        self, workspace: Path, request: ProviderExecutionRequest, timeout: int
    ) -> dict[str, object]:
        (workspace / "backend" / "app" / "beacon" / "result.py").write_text(
            "VALUE = 1\n"
        )
        return {"implementation": "test"}


def git(path: Path, *argv: str) -> str:
    result = subprocess.run(
        ("git", *argv), cwd=path, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


@pytest.fixture
def repository(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repository"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.invalid")
    (root / "backend" / "app" / "beacon").mkdir(parents=True)
    (root / "backend" / "app" / "beacon" / "initial.py").write_text("VALUE = 0\n")
    git(root, "add", ".")
    git(root, "commit", "-m", "initial")
    return root, git(root, "rev-parse", "HEAD")


def make_request(head: str, **changes: object) -> ProviderExecutionRequest:
    instruction = "Implement the bounded Beacon definition."
    boundary = ProviderBoundary(
        allowed_repository="acp-enterprise",
        allowed_branch="main",
        expected_head=head,
        allowed_paths=("backend/app/beacon/**",),
        forbidden_paths=(".git/**", ".env*", "**/.env*"),
        permitted_operations=("inspect", "modify", "validate", "commit"),
        validation_requirements=("git diff --check",),
    )
    values = {
        "company_id": uuid4(),
        "node_id": uuid4(),
        "command_id": uuid4(),
        "execution_id": uuid4(),
        "lease_id": uuid4(),
        "workspace_id": "bea6-execution",
        "instruction": instruction,
        "instruction_digest": hashlib.sha256(instruction.encode()).hexdigest(),
        "request_digest": "a" * 64,
        "boundary_digest": boundary_digest(boundary),
        "boundary": boundary,
        "commit_subject": "feat(beacon): define economics signals",
    }
    values.update(changes)
    return ProviderExecutionRequest(**values)


def service(tmp_path: Path, repository: Path) -> ControlledExecutionProvider:
    return ControlledExecutionProvider(
        WorkspaceManager(tmp_path / "provider", {"acp-enterprise": repository}),
        ProviderJournal(tmp_path / "journal"),
        Implementation(),
    )


def test_provider_owns_workspace_validation_and_commit(
    repository: tuple[Path, str], tmp_path: Path
) -> None:
    root, head = repository
    result = service(tmp_path, root).execute(make_request(head))
    assert result.phase is ProviderPhase.COMPLETED
    assert result.starting_head == head
    assert result.commit_sha and result.commit_sha != head
    assert result.files_changed == ("backend/app/beacon/result.py",)
    assert git(root, "status", "--porcelain") == ""


def test_boundary_digest_tampering_fails_before_workspace(
    repository: tuple[Path, str], tmp_path: Path
) -> None:
    root, head = repository
    with pytest.raises(BoundaryViolation, match="digest"):
        service(tmp_path, root).execute(make_request(head, boundary_digest="0" * 64))
    assert not tuple((tmp_path / "provider" / "executions").glob("*"))


def test_duplicate_completed_execution_is_rejected(
    repository: tuple[Path, str], tmp_path: Path
) -> None:
    root, head = repository
    request = make_request(head)
    provider = service(tmp_path, root)
    provider.execute(request)
    with pytest.raises(ProviderFailure, match="Duplicate"):
        provider.execute(request)
