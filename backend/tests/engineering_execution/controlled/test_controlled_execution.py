import json
from pathlib import Path
from uuid import uuid4

import pytest
from app.engineering_execution.controlled.service import _valid_failed_output
from app.worker_runtime.execution import (
    AcquiredControlledOffer,
    IsolatedWorkspaceExecutionError,
    IsolatedWorkspaceExecutor,
)

HEAD = "a" * 40


def offer(**payload_overrides) -> AcquiredControlledOffer:
    payload = {
        "manifest_name": "workspace-manifest.json",
        "expected_branch": "df9-demo",
        "expected_head": HEAD,
        "repository_key": "acp-enterprise",
        "repository_mutation_allowed": False,
        **payload_overrides,
    }
    return AcquiredControlledOffer(
        offer_id=uuid4(),
        lease_id=uuid4(),
        lease_version=1,
        workspace_id="df9c-demo",
        command_type="inspect_workspace",
        payload=payload,
    )


def workspace(root: Path, **overrides) -> Path:
    target = root / "df9c-demo"
    target.mkdir()
    manifest = {
        "schema_version": "1",
        "workspace_id": "df9c-demo",
        "repository_key": "acp-enterprise",
        "branch": "df9-demo",
        "head": HEAD,
        "clean": True,
        "file_boundary": ["README.md", "backend/app/main.py"],
        **overrides,
    }
    (target / "workspace-manifest.json").write_text(json.dumps(manifest))
    return target


def test_read_only_workspace_inspection_is_bounded_and_deterministic(
    tmp_path: Path,
) -> None:
    workspace(tmp_path)

    result = IsolatedWorkspaceExecutor(tmp_path).execute(offer())

    assert result == {
        "workspace_id": "df9c-demo",
        "repository_key": "acp-enterprise",
        "branch": "df9-demo",
        "head": HEAD,
        "clean": True,
        "file_count": 2,
        "file_boundary": ("README.md", "backend/app/main.py"),
        "repository_mutated": False,
    }


@pytest.mark.parametrize(
    ("manifest", "payload"),
    [
        ({"branch": "wrong"}, {}),
        ({"head": "b" * 40}, {}),
        ({"clean": False}, {}),
        ({"repository_key": "other"}, {}),
        ({"file_boundary": ["../outside"]}, {}),
        ({"file_boundary": [".git/config"]}, {}),
        ({"file_boundary": ["z.py", "a.py"]}, {}),
        ({}, {"manifest_name": "../workspace-manifest.json"}),
    ],
)
def test_workspace_evidence_mismatch_fails_closed(
    tmp_path: Path,
    manifest: dict[str, object],
    payload: dict[str, object],
) -> None:
    workspace(tmp_path, **manifest)

    with pytest.raises(IsolatedWorkspaceExecutionError):
        IsolatedWorkspaceExecutor(tmp_path).execute(offer(**payload))


def test_workspace_symlink_escape_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "df9c-demo").symlink_to(outside, target_is_directory=True)

    with pytest.raises(IsolatedWorkspaceExecutionError):
        IsolatedWorkspaceExecutor(tmp_path).execute(offer())


def test_arbitrary_command_type_is_rejected(tmp_path: Path) -> None:
    workspace(tmp_path)
    invalid = AcquiredControlledOffer(**{**offer().__dict__, "command_type": "shell"})

    with pytest.raises(IsolatedWorkspaceExecutionError):
        IsolatedWorkspaceExecutor(tmp_path).execute(invalid)


def test_runtime_module_exposes_no_shell_or_repository_authority() -> None:
    source = Path("app/worker_runtime/execution.py").read_text()

    assert "subprocess" not in source
    assert "shell=True" not in source
    assert "git add" not in source
    assert "git commit" not in source
    assert "docker" not in source.lower()


def failed_output() -> dict[str, object]:
    return {
        "workspace_id": "df9c-demo",
        "repository_key": "acp-enterprise",
        "branch": "df9-demo",
        "starting_head": HEAD,
        "file_count": 1,
        "file_boundary": ["frontend/src/features/technician/Shell.tsx"],
        "validation": {"frontend tests": False},
        "validation_runs": [
            {
                "identity": "frontend tests",
                "argv": ["npm", "run", "test:run"],
                "working_directory": "frontend",
                "started_at": "2026-08-13T12:00:00+00:00",
                "completed_at": "2026-08-13T12:00:01+00:00",
                "duration_ms": 1000,
                "exit_code": 1,
                "passed": False,
                "failure_summary": "FAIL TechnicianShell",
                "toolchain": {"node_version": "22.23.1"},
                "stdout": {
                    "text": "FAIL TechnicianShell",
                    "truncated": False,
                    "redacted": False,
                },
                "stderr": {
                    "text": "expected Ready",
                    "truncated": False,
                    "redacted": False,
                },
            }
        ],
        "validation_environment": {"lockfile_sha256": "a" * 64},
        "implementation_summary": "Implemented bounded shell.",
        "repository_mutated": False,
    }


def test_failed_controlled_result_requires_bounded_diagnostics() -> None:
    assert _valid_failed_output(failed_output()) is True
    missing = failed_output()
    missing["validation_runs"] = []
    assert _valid_failed_output(missing) is False


def test_failed_controlled_result_rejects_unredacted_sensitive_output() -> None:
    output = failed_output()
    run = dict(output["validation_runs"][0])
    run["stderr"] = {
        "text": "TOKEN=should-not-persist",
        "truncated": False,
        "redacted": False,
    }
    output["validation_runs"] = [run]
    assert _valid_failed_output(output) is False
