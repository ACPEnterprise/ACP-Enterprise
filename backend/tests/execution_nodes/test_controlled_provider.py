import hashlib
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from app.engineering_control.revision_evidence import compose_revision_instruction
from app.execution_nodes.boundaries import BoundaryViolation, boundary_digest
from app.execution_nodes.contracts import (
    ProviderBoundary,
    ProviderExecutionRequest,
    ProviderPhase,
)
from app.execution_nodes.provider import (
    ControlledExecutionProvider,
    FrontendValidationEnvironment,
    ProviderFailure,
    ProviderJournal,
    prepare_writable_roots,
)
from app.execution_nodes.workspaces import WorkspaceFailure, WorkspaceManager


class Implementation:
    def execute(
        self, workspace: Path, request: ProviderExecutionRequest, timeout: int
    ) -> dict[str, object]:
        (workspace / "backend" / "app" / "beacon" / "result.py").write_text(
            "VALUE = 1\n"
        )
        return {"implementation": "test"}


class FrontendImplementation:
    def __init__(self, content: str) -> None:
        self.content = content

    def execute(
        self, workspace: Path, request: ProviderExecutionRequest, timeout: int
    ) -> dict[str, object]:
        target = workspace / "frontend" / "src" / "features" / "technician"
        target.mkdir(parents=True, exist_ok=True)
        (target / "TechnicianShell.tsx").write_text(self.content)
        return {"summary": "Implemented the bounded Technician shell fixture."}


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
    git(
        repository,
        "update-ref",
        "refs/acp/provider-ready/main",
        git(repository, "rev-parse", "main"),
    )
    return ControlledExecutionProvider(
        WorkspaceManager(tmp_path / "provider", {"acp-enterprise": repository}),
        ProviderJournal(tmp_path / "journal"),
        Implementation(),
    )


def test_repository_readiness_prepares_provider_owned_ref_without_moving_branch(
    repository: tuple[Path, str], tmp_path: Path
) -> None:
    root, head = repository
    manager = WorkspaceManager(tmp_path / "provider", {"acp-enterprise": root})
    evidence = manager.prepare_repository("acp-enterprise", "main", head)
    assert evidence.ready is True
    assert evidence.observed_head == head
    assert git(root, "rev-parse", "main") == head
    assert git(root, "rev-parse", "refs/acp/provider-ready/main") == head


def test_repository_readiness_refuses_dirty_checkout_without_data_loss(
    repository: tuple[Path, str], tmp_path: Path
) -> None:
    root, head = repository
    marker = root / "local-evidence.txt"
    marker.write_text("preserve me\n")
    manager = WorkspaceManager(tmp_path / "provider", {"acp-enterprise": root})
    with pytest.raises(WorkspaceFailure, match="dirty"):
        manager.prepare_repository("acp-enterprise", "main", head)
    assert marker.read_text() == "preserve me\n"
    assert git(root, "rev-parse", "main") == head


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


def _frontend_validation_environment(tmp_path: Path) -> FrontendValidationEnvironment:
    tools = tmp_path / "tools"
    tools.mkdir()
    node = tools / "node"
    node.write_text("#!/bin/sh\necho v22.23.1\n")
    node.chmod(0o755)
    npm = tools / "npm"
    npm.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "--version" ]; then echo 10.9.8; exit 0; fi\n'
        'printf \'%s\\n\' "$*|$NPM_CONFIG_OFFLINE|$NPM_CONFIG_IGNORE_SCRIPTS" >> "$NPM_CONFIG_CACHE/calls"\n'
        'if [ "$1" = "ci" ]; then mkdir -p node_modules; : > node_modules/.package-lock.json; fi\n'
    )
    npm.chmod(0o755)
    return FrontendValidationEnvironment(
        node,
        npm,
        tmp_path / "npm-cache",
        expected_node_version="22.23.1",
        expected_npm_version="10.9.8",
    )


def test_frontend_dependencies_are_prepared_offline_without_scripts(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    frontend = workspace / "frontend"
    frontend.mkdir(parents=True)
    (frontend / "package.json").write_text("{}\n")
    (frontend / "package-lock.json").write_text('{"lockfileVersion":3}\n')
    environment = _frontend_validation_environment(tmp_path)

    evidence = environment.prepare(workspace)

    assert evidence["mode"] == "npm-ci-offline-ignore-scripts"
    assert evidence["node_version"] == "22.23.1"
    assert evidence["npm_version"] == "10.9.8"
    calls = (tmp_path / "npm-cache" / "calls").read_text()
    assert "ci --ignore-scripts --offline --no-audit --no-fund|true|true" in calls


def test_frontend_validation_uses_prepared_pinned_toolchain(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    frontend = workspace / "frontend"
    frontend.mkdir(parents=True)
    (frontend / "package.json").write_text("{}\n")
    (frontend / "package-lock.json").write_text('{"lockfileVersion":3}\n')
    environment = _frontend_validation_environment(tmp_path)
    environment.prepare(workspace)
    provider = ControlledExecutionProvider(
        WorkspaceManager(tmp_path / "provider", {}),
        ProviderJournal(tmp_path / "journal"),
        Implementation(),
        environment,
    )

    results, runs = provider._validate(
        workspace,
        ("frontend tests", "eslint", "typescript"),
        ("frontend/src/features/technician/TechnicianShell.tsx",),
    )

    assert results == {"frontend tests": True, "eslint": True, "typescript": True}
    assert [run["identity"] for run in runs] == [
        "frontend tests",
        "eslint",
        "typescript",
    ]
    assert all(run["exit_code"] == 0 for run in runs)
    calls = (tmp_path / "npm-cache" / "calls").read_text()
    assert "run test:run|true|true" in calls
    assert "run lint -- --max-warnings=0|true|true" in calls
    assert "run build|true|true" in calls
    assert not (frontend / "node_modules" / ".tmp").exists()
    assert not (frontend / "dist").exists()


def test_validation_failure_preserves_bounded_redacted_diagnostics(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    frontend = workspace / "frontend"
    frontend.mkdir(parents=True)
    (frontend / "package.json").write_text("{}\n")
    (frontend / "package-lock.json").write_text('{"lockfileVersion":3}\n')
    environment = _frontend_validation_environment(tmp_path)
    environment.prepare(workspace)
    npm = environment.npm_executable
    npm.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "--version" ]; then echo 10.9.8; exit 0; fi\n'
        'echo "AssertionError: expected Ready"\n'
        'echo "TOKEN=must-not-survive" >&2\n'
        "yes x | head -c 20000\n"
        "exit 7\n"
    )
    provider = ControlledExecutionProvider(
        WorkspaceManager(tmp_path / "provider", {}),
        ProviderJournal(tmp_path / "journal"),
        Implementation(),
        environment,
    )

    results, runs = provider._validate(
        workspace,
        ("frontend tests",),
        ("frontend/src/features/technician/TechnicianShell.tsx",),
    )

    assert results == {"frontend tests": False}
    run = runs[0]
    assert run["exit_code"] == 7
    assert run["passed"] is False
    assert run["duration_ms"] >= 0
    assert run["stdout"]["truncated"] is True
    assert "AssertionError: expected Ready" in run["stdout"]["text"]
    assert run["stderr"]["redacted"] is True
    assert "must-not-survive" not in run["stderr"]["text"]


def test_isolated_failed_validation_revision_publishes_from_new_workspace(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.invalid")
    frontend = root / "frontend"
    (frontend / "src").mkdir(parents=True)
    (frontend / "package.json").write_text("{}\n")
    (frontend / "package-lock.json").write_text('{"lockfileVersion":3}\n')
    (root / ".gitignore").write_text("frontend/node_modules/\nfrontend/dist/\n")
    git(root, "add", ".")
    git(root, "commit", "-m", "initial")
    remote = tmp_path / "remote.git"
    subprocess.run(("git", "init", "--bare", str(remote)), check=True)
    git(root, "remote", "add", "origin", str(remote))
    git(root, "push", "-u", "origin", "main")
    head = git(root, "rev-parse", "HEAD")
    git(root, "update-ref", "refs/acp/provider-ready/main", head)
    boundary = ProviderBoundary(
        allowed_repository="acp-enterprise",
        allowed_branch="main",
        expected_head=head,
        allowed_paths=("frontend/src/features/technician/**",),
        forbidden_paths=(".git/**", ".env*", "**/.env*", "backend/**"),
        permitted_operations=(
            "inspect",
            "modify",
            "validate",
            "commit",
            "mechanical_reconcile",
            "push",
        ),
        validation_requirements=(
            "frontend tests",
            "eslint",
            "typescript",
            "git diff --check",
        ),
    )
    environment = _frontend_validation_environment(tmp_path)
    npm = environment.npm_executable
    npm.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "--version" ]; then echo 10.9.8; exit 0; fi\n'
        'if [ "$1" = "ci" ]; then mkdir -p node_modules; : > node_modules/.package-lock.json; exit 0; fi\n'
        'echo "FAIL TechnicianShell renders an unsafe state" >&2\n'
        "exit 1\n"
    )
    manager = WorkspaceManager(tmp_path / "provider", {"acp-enterprise": root})
    first = make_request(
        head,
        workspace_id="tech-first-attempt",
        boundary=boundary,
        boundary_digest=boundary_digest(boundary),
        instruction="Establish the bounded Technician shell.",
        instruction_digest=hashlib.sha256(
            b"Establish the bounded Technician shell."
        ).hexdigest(),
        commit_subject="feat(technician): establish application shell",
    )
    failed = ControlledExecutionProvider(
        manager,
        ProviderJournal(tmp_path / "journal"),
        FrontendImplementation("export const broken = true;\n"),
        environment,
    ).execute(first)
    assert failed.phase is ProviderPhase.FAILED
    assert failed.commit_sha is None
    assert failed.evidence["validation_runs"]
    assert git(root, "ls-remote", "origin", "refs/heads/main").split()[0] == head
    historical = (
        manager.root / "executions" / str(first.company_id) / first.workspace_id
    )
    assert git(historical, "status", "--porcelain")

    revision_instruction = compose_revision_instruction(
        milestone_instruction="Establish the bounded Technician shell.",
        prior_execution_id=str(first.execution_id),
        failure_classification="required_validation_failed",
        implementation_summary=str(failed.evidence.get("summary", "")),
        changed_paths=failed.files_changed,
        validation_runs=failed.evidence["validation_runs"],
    )
    npm.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "--version" ]; then echo 10.9.8; exit 0; fi\n'
        'if [ "$1" = "ci" ]; then mkdir -p node_modules; : > node_modules/.package-lock.json; fi\n'
        "exit 0\n"
    )
    second = make_request(
        head,
        command_id=uuid4(),
        execution_id=uuid4(),
        lease_id=uuid4(),
        workspace_id="tech-revision-attempt",
        boundary=boundary,
        boundary_digest=boundary_digest(boundary),
        instruction=revision_instruction,
        instruction_digest=hashlib.sha256(revision_instruction.encode()).hexdigest(),
        commit_subject="feat(technician): establish application shell",
    )
    succeeded = ControlledExecutionProvider(
        manager,
        ProviderJournal(tmp_path / "journal"),
        FrontendImplementation("export const technicianShell = true;\n"),
        environment,
    ).execute(second)
    assert second.execution_id != first.execution_id
    assert succeeded.phase is ProviderPhase.COMPLETED
    assert succeeded.commit_sha is not None
    assert all(succeeded.validation.values())
    assert (
        git(root, "ls-remote", "origin", "refs/heads/main").split()[0]
        == succeeded.commit_sha
    )
    assert git(historical, "status", "--porcelain")
    assert str(first.execution_id) in revision_instruction
    assert "immutable historical evidence" in revision_instruction


def test_frontend_validation_discards_only_generated_build_artifacts(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    frontend = workspace / "frontend"
    (frontend / "node_modules" / ".tmp").mkdir(parents=True)
    (frontend / "node_modules" / ".tmp" / "build.info").write_text("generated")
    (frontend / "dist").mkdir()
    (frontend / "dist" / "index.html").write_text("generated")
    (frontend / "src").mkdir()
    product = frontend / "src" / "product.ts"
    product.write_text("export const value = 1;\n")

    FrontendValidationEnvironment.clean_generated_artifacts(workspace)

    assert not (frontend / "node_modules" / ".tmp").exists()
    assert not (frontend / "dist").exists()
    assert product.read_text() == "export const value = 1;\n"


def test_frontend_validation_fails_before_execution_when_not_configured(
    repository: tuple[Path, str], tmp_path: Path
) -> None:
    root, head = repository
    request = make_request(head)
    boundary = ProviderBoundary(
        **{
            **request.boundary.__dict__,
            "validation_requirements": ("typescript",),
        }
    )
    request = ProviderExecutionRequest(
        **{
            **request.__dict__,
            "boundary": boundary,
            "boundary_digest": boundary_digest(boundary),
        }
    )

    with pytest.raises(ProviderFailure, match="not configured"):
        service(tmp_path, root).execute(request)

    journal = ProviderJournal(tmp_path / "journal")
    assert journal.latest_phase(request) is ProviderPhase.COMPOSED
    assert git(root, "status", "--porcelain") == ""


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


def test_read_only_provider_validates_without_implementation_or_publication(
    repository: tuple[Path, str], tmp_path: Path
) -> None:
    root, head = repository
    boundary = ProviderBoundary(
        allowed_repository="acp-enterprise",
        allowed_branch="main",
        expected_head=head,
        allowed_paths=("**",),
        forbidden_paths=(".git/**", ".env*", "**/.env*"),
        permitted_operations=("inspect", "validate"),
        validation_requirements=("git diff --check",),
    )
    request = make_request(
        head,
        boundary=boundary,
        boundary_digest=boundary_digest(boundary),
        execution_capability_profile="inspect_validate_only",
        repository_mutation_allowed=False,
    )
    before = git(root, "ls-remote", "origin", "refs/heads/main").split()[0]
    result = service(tmp_path, root).execute(request)
    assert result.phase is ProviderPhase.COMPLETED
    assert result.result_head == head
    assert result.commit_sha is None
    assert result.files_changed == ()
    assert result.evidence["repository_mutated"] is False
    assert result.evidence["phases"] == [
        "composed", "workspace_ready", "validating", "completed"
    ]
    assert git(root, "ls-remote", "origin", "refs/heads/main").split()[0] == before


def test_read_only_profile_rejects_mutation_operations(
    repository: tuple[Path, str], tmp_path: Path
) -> None:
    root, head = repository
    request = make_request(
        head,
        execution_capability_profile="inspect_validate_only",
        repository_mutation_allowed=False,
    )
    with pytest.raises(BoundaryViolation, match="Read-only"):
        service(tmp_path, root).execute(request)


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
