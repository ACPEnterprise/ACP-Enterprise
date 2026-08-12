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
    prepare_writable_roots,
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
    remote = tmp_path / "remote.git"
    subprocess.run(("git", "init", "--bare", str(remote)), check=True)
    git(root, "remote", "add", "origin", str(remote))
    git(root, "push", "-u", "origin", "main")
    return root, git(root, "rev-parse", "HEAD")


def make_request(head: str, **changes: object) -> ProviderExecutionRequest:
    instruction = "Implement the bounded Beacon definition."
    boundary = ProviderBoundary(
        allowed_repository="acp-enterprise",
        allowed_branch="main",
        expected_head=head,
        allowed_paths=("backend/app/beacon/**",),
        forbidden_paths=(".git/**", ".env*", "**/.env*"),
        permitted_operations=(
            "inspect",
            "modify",
            "validate",
            "commit",
            "mechanical_reconcile",
            "push",
        ),
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


def advance_remote(repository: Path, tmp_path: Path, relative: str) -> str:
    clone = tmp_path / f"advance-{relative.replace('/', '-')}"
    subprocess.run(
        (
            "git",
            "clone",
            "--branch",
            "main",
            str(repository.parent / "remote.git"),
            str(clone),
        ),
        check=True,
    )
    git(clone, "config", "user.name", "Remote Test")
    git(clone, "config", "user.email", "remote@example.invalid")
    target = clone / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("REMOTE = 1\n")
    git(clone, "add", relative)
    git(clone, "commit", "-m", "remote advance")
    git(clone, "push", "origin", "main")
    return git(clone, "rev-parse", "HEAD")


def test_provider_owns_workspace_validation_and_commit(
    repository: tuple[Path, str], tmp_path: Path
) -> None:
    root, head = repository
    result = service(tmp_path, root).execute(make_request(head))
    assert result.phase is ProviderPhase.COMPLETED
    assert result.starting_head == head
    assert result.commit_sha and result.commit_sha != head
    assert (
        git(root, "ls-remote", "origin", "refs/heads/main").split()[0]
        == result.commit_sha
    )
    assert result.files_changed == ("backend/app/beacon/result.py",)
    assert git(root, "status", "--porcelain") == ""


def test_boundary_digest_tampering_fails_before_workspace(
    repository: tuple[Path, str], tmp_path: Path
) -> None:
    root, head = repository
    with pytest.raises(BoundaryViolation, match="digest"):
        service(tmp_path, root).execute(make_request(head, boundary_digest="0" * 64))
    assert not tuple((tmp_path / "provider" / "executions").glob("*"))


def test_absent_authorized_directory_is_prepared_without_parent_expansion(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "docs" / "architecture").mkdir(parents=True)

    roots = prepare_writable_roots(workspace, ("docs/architecture/technician/**",))

    technician = workspace / "docs" / "architecture" / "technician"
    assert roots == (technician.resolve(),)
    assert technician.is_dir()
    assert workspace / "docs" / "architecture" not in roots


def test_absent_authorized_directory_rejects_existing_symlink_escape(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (workspace / "docs").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ProviderFailure, match="invalid existing ancestor"):
        prepare_writable_roots(workspace, ("docs/architecture/technician/**",))


def test_filename_boundaries_prepare_only_the_containing_directory(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    routes = workspace / "frontend" / "src" / "routes"
    routes.mkdir(parents=True)
    router = workspace / "frontend" / "src" / "routing" / "router.tsx"
    router.parent.mkdir(parents=True)
    router.write_text("export {}\n")

    roots = prepare_writable_roots(
        workspace,
        (
            "frontend/src/routes/Technician*.tsx",
            "frontend/src/routing/router.tsx",
        ),
    )

    assert roots == (routes.resolve(), router.parent.resolve())


@pytest.mark.parametrize(
    "pattern",
    ("../outside/**", "/tmp/outside/**", "docs/../outside/**"),
)
def test_writable_root_preparation_rejects_traversal_and_absolute_escape(
    tmp_path: Path, pattern: str
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(ProviderFailure, match="unsafe"):
        prepare_writable_roots(workspace, (pattern,))


@pytest.mark.parametrize(
    "changed",
    (
        "docs/architecture/other-domain/file.md",
        "docs/architecture/parent.md",
        "backend/app/technician/service.py",
        "backend/alembic/versions/unsafe.py",
        "docker-compose.preview.yml",
        ".env.preview",
    ),
)
def test_tech_boundary_rejects_paths_outside_absent_authorized_root(
    changed: str,
) -> None:
    boundary = ProviderBoundary(
        allowed_repository="acp-enterprise",
        allowed_branch="customer-management-v1",
        expected_head="a" * 40,
        allowed_paths=("docs/architecture/technician/**",),
        forbidden_paths=(
            ".git/**",
            ".env*",
            "**/.env*",
            "backend/alembic/**",
            "docker-compose*.yml",
        ),
        permitted_operations=(
            "inspect",
            "modify",
            "validate",
            "commit",
            "mechanical_reconcile",
            "push",
        ),
        validation_requirements=("git diff --check",),
    )

    from app.execution_nodes.boundaries import enforce_changed_paths

    with pytest.raises(BoundaryViolation):
        enforce_changed_paths(boundary, (changed,))


def test_duplicate_completed_execution_is_rejected(
    repository: tuple[Path, str], tmp_path: Path
) -> None:
    root, head = repository
    request = make_request(head)
    provider = service(tmp_path, root)
    provider.execute(request)
    with pytest.raises(ProviderFailure, match="Duplicate"):
        provider.execute(request)


def test_provider_mechanically_reconciles_disjoint_remote_advance(
    repository: tuple[Path, str], tmp_path: Path
) -> None:
    root, head = repository
    remote_head = advance_remote(root, tmp_path, "docs/remote.md")
    result = service(tmp_path, root).execute(make_request(head))
    assert result.evidence["mechanically_reconciled"] is True
    assert result.evidence["remote_head_before"] == remote_head
    assert (
        git(root, "ls-remote", "origin", "refs/heads/main").split()[0]
        == result.commit_sha
    )


def test_provider_fails_closed_on_overlapping_remote_advance(
    repository: tuple[Path, str], tmp_path: Path
) -> None:
    root, head = repository
    advance_remote(root, tmp_path, "backend/app/beacon/result.py")
    with pytest.raises(ProviderFailure, match="serialized owner-reviewed"):
        service(tmp_path, root).execute(make_request(head))
