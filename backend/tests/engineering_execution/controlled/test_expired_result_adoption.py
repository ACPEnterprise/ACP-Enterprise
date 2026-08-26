import hashlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.engineering_control.scheduler.manifest import release_bound_manifest
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
    "mismatch",
    [None, "workstream", "repository", "starting_head", "fingerprint", "after_fact"],
)
@pytest.mark.asyncio
async def test_legacy_boundary_composes_from_precommand_scheduler_provenance(
    mismatch: str | None,
) -> None:
    start = "a" * 40
    manifest = release_bound_manifest(start)
    definition = next(
        item for item in manifest.milestones if item.milestone_code == "TECH.1"
    )
    assert definition.execution_boundary is not None
    legacy = {
        "allowed_repository": definition.repository_key,
        "allowed_branch": "customer-management-v1",
        "expected_head": start,
        "allowed_paths": list(definition.execution_boundary.allowed_paths),
        "forbidden_paths": list(definition.execution_boundary.forbidden_paths),
        "permitted_operations": list(
            definition.execution_boundary.permitted_operations
        ),
        "validation_requirements": list(
            definition.execution_boundary.validation_requirements
        ),
    }
    digest = hashlib.sha256(
        json.dumps(legacy, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    command_id, execution_id, milestone_id = uuid4(), uuid4(), uuid4()
    command = SimpleNamespace(
        id=command_id,
        company_id=uuid4(),
        repository_key=definition.repository_key,
        expected_branch="customer-management-v1",
        expected_head=start,
        execution_boundary=legacy,
        execution_boundary_digest=digest,
        created_at=NOW,
        approved_at=NOW,
    )
    execution = SimpleNamespace(id=execution_id, command_id=command_id)
    milestone = SimpleNamespace(
        id=milestone_id,
        roadmap_id=uuid4(),
        milestone_code="TECH.1",
        owning_workstream=definition.workstream,
        owning_branch="customer-management-v1",
    )
    roadmap = SimpleNamespace(
        company_id=command.company_id,
        repository_key=command.repository_key,
        expected_branch=command.expected_branch,
    )
    historical_at = NOW.replace(minute=NOW.minute - 1)
    event = SimpleNamespace(
        id=uuid4(),
        scheduler_version=manifest.scheduler_version,
        occurred_at=historical_at,
    )
    snapshot = SimpleNamespace(
        id=uuid4(),
        scheduler_version=manifest.scheduler_version,
        fingerprint=manifest.fingerprint,
        manifest=manifest.model_dump(mode="json"),
        created_at=historical_at,
        activated_at=historical_at,
    )
    requested_head = start
    requested_fingerprint = definition.execution_boundary.fingerprint
    if mismatch == "workstream":
        milestone.owning_workstream = "Different workstream"
    elif mismatch == "repository":
        roadmap.repository_key = "different-repository"
    elif mismatch == "starting_head":
        requested_head = "b" * 40
    elif mismatch == "fingerprint":
        requested_fingerprint = "0" * 64
    elif mismatch == "after_fact":
        event.occurred_at = NOW.replace(minute=NOW.minute + 1)
    session = AsyncMock()
    session.scalars.side_effect = [
        SimpleNamespace(all=lambda: [milestone]),
        SimpleNamespace(all=lambda: [event]),
    ]
    session.get.return_value = roadmap
    session.scalar.return_value = snapshot
    operation = ControlledExecutionService._resolve_adoption_boundary(
        session,
        command=command,
        execution=execution,
        starting_head=requested_head,
        boundary_version=definition.execution_boundary.boundary_version,
        boundary_fingerprint=requested_fingerprint,
    )
    if mismatch is not None:
        with pytest.raises(ControlledExecutionPayloadError):
            await operation
        return
    composed, provenance = await operation
    assert command.execution_boundary == legacy
    assert "boundary_version" not in command.execution_boundary
    assert composed["boundary_version"] == 2
    assert provenance["source"] == "legacy_scheduler_snapshot"
    assert provenance["scheduler_event_id"] == str(event.id)


@pytest.mark.asyncio
async def test_partial_frozen_boundary_metadata_rejects_legacy_composition() -> None:
    command = SimpleNamespace(
        execution_boundary={"boundary_version": 2},
        execution_boundary_digest=hashlib.sha256(
            b'{"boundary_version":2}'
        ).hexdigest(),
    )
    with pytest.raises(ControlledExecutionPayloadError):
        await ControlledExecutionService._resolve_adoption_boundary(
            AsyncMock(),
            command=command,
            execution=SimpleNamespace(),
            starting_head="a" * 40,
            boundary_version=2,
            boundary_fingerprint="0" * 64,
        )


@pytest.mark.parametrize(
    "path",
    ["backend/app/main.py", "frontend/src/layout/ApplicationShell.tsx", "../escape"],
)
def test_expired_lineage_adoption_rejects_paths_outside_frozen_boundary(
    path: str,
) -> None:
    with pytest.raises(ControlledExecutionPayloadError):
        validate(path)
