from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.engineering_execution.controlled.errors import ControlledExecutionPayloadError
from app.engineering_execution.controlled.service import ControlledExecutionService

NOW = datetime(2026, 8, 26, 18, 24, 8, tzinfo=timezone.utc)
START = "f" * 40
COMMIT = "7" * 40
FINGERPRINT = "0" * 64
DIGEST = "8" * 64
PATH = "frontend/src/api/technician.ts"


def validation_run(identity: str) -> dict[str, object]:
    return {
        "identity": identity,
        "argv": ["tool", identity],
        "working_directory": ".",
        "started_at": NOW.isoformat(),
        "completed_at": NOW.isoformat(),
        "duration_ms": 1,
        "exit_code": 0,
        "passed": True,
        "failure_summary": None,
        "toolchain": {"version": "test"},
        "stdout": {"text": "passed", "truncated": False, "redacted": False},
        "stderr": {"text": "", "truncated": False, "redacted": False},
    }


def source(path: str = PATH) -> tuple[object, object, object, dict[str, object]]:
    requirements = ["git diff --check", "pytest"]
    boundary = {
        "boundary_version": 2,
        "fingerprint": FINGERPRINT,
        "allowed_paths": ["frontend/src/api/technician*.ts"],
        "forbidden_paths": ["backend/**", ".env*"],
        "validation_requirements": requirements,
    }
    command = SimpleNamespace(
        expected_head=START,
        execution_boundary_digest=DIGEST,
        execution_boundary=boundary,
    )
    execution = SimpleNamespace(
        state="running",
        started_at=NOW,
        evidence_summary={
            "reconciliation_required": True,
            "reconciliation_reason": "expired_lease_unresolved_provider_outcome",
        },
    )
    offer = SimpleNamespace(state="expired", id=uuid4())
    validations = {name: True for name in requirements}
    output: dict[str, object] = {
        "workspace_id": "execution-test",
        "repository_key": "acp-enterprise",
        "branch": "customer-management-v1",
        "head": COMMIT,
        "starting_head": START,
        "commit_sha": COMMIT,
        "published_commit_sha": COMMIT,
        "remote_head_before": START,
        "mechanically_reconciled": False,
        "clean": True,
        "file_count": 1,
        "file_boundary": [path],
        "repository_mutated": True,
        "validation": validations,
        "validation_runs": [validation_run(name) for name in requirements],
        "validation_environment": {"mode": "isolated"},
        "evidence": {
            "phases": [
                "composed",
                "workspace_ready",
                "executing",
                "validating",
                "commit_ready",
                "publishing_result",
                "completed",
            ]
        },
    }
    return command, execution, offer, output


def validate(path: str = PATH) -> None:
    command, execution, offer, output = source(path)
    ControlledExecutionService._validate_adoption_source(
        command=command,  # type: ignore[arg-type]
        execution=execution,  # type: ignore[arg-type]
        offer=offer,  # type: ignore[arg-type]
        starting_head=START,
        commit_sha=COMMIT,
        commit_parent=START,
        remote_head=COMMIT,
        boundary_version=2,
        boundary_fingerprint=FINGERPRINT,
        boundary_digest=DIGEST,
        provider_completed_at=NOW,
        workspace_clean=True,
        output=output,
    )


def test_complete_published_expired_lineage_is_eligible() -> None:
    validate()


@pytest.mark.parametrize(
    "path",
    ["backend/app/main.py", "frontend/src/layout/ApplicationShell.tsx", "../escape"],
)
def test_expired_lineage_adoption_rejects_paths_outside_frozen_boundary(
    path: str,
) -> None:
    with pytest.raises(ControlledExecutionPayloadError):
        validate(path)
