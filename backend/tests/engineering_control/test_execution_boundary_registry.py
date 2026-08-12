from copy import deepcopy

import pytest

from app.engineering_control.errors import EngineeringCommandValidationError
from app.engineering_control.mobile.roadmaps import RoadmapService
from app.engineering_control.scheduler.manifest import (
    ExecutionBoundaryDefinition,
    load_scheduler_manifest,
    manifest_fingerprint,
)
from app.engineering_control.service import EngineeringControlService
from app.execution_nodes.boundaries import BoundaryViolation, enforce_changed_paths
from app.execution_nodes.contracts import ProviderBoundary


def _tech_contract() -> tuple[dict[str, object], dict[str, object]]:
    manifest = load_scheduler_manifest()
    milestone = next(
        item for item in manifest.milestones if item.milestone_code == "TECH.1"
    )
    assert milestone.execution_boundary is not None
    evidence = {
        "execution_boundary": milestone.execution_boundary.model_dump(mode="json")
    }
    resolved = RoadmapService._execution_boundary(
        repository_key="acp-enterprise",
        expected_branch="customer-management-v1",
        expected_head="9c2b114cb658be0454bbb36bdf0e5929ecc7e0e5",
        milestone_code="TECH.1",
        owning_workstream="Field Service",
        starting_commit_evidence=evidence,
        validation=(),
        requested_code_changes=True,
    )
    return evidence, resolved


def test_tech_boundary_resolves_and_composes_deterministically() -> None:
    _, first = _tech_contract()
    _, second = _tech_contract()
    assert first == second
    assert first["allowed_paths"] == [
        "frontend/src/features/technician/**",
        "frontend/src/routes/Technician*.tsx",
        "frontend/src/api/technician*.ts",
        "frontend/src/hooks/useTechnician*.ts",
        "frontend/src/types/technician*.ts",
        "frontend/src/routing/router.tsx",
        "frontend/src/routing/router.test.tsx",
        "frontend/src/routing/routeMetadata.ts",
        "frontend/src/routing/routeMetadata.test.ts",
        "frontend/src/layout/navigation.ts",
        "frontend/src/layout/navigation.test.ts",
        "docs/architecture/technician/**",
    ]
    normalized = EngineeringControlService._normalize_execution_boundary(
        first,
        repository_key="acp-enterprise",
        expected_branch="customer-management-v1",
        expected_head="9c2b114cb658be0454bbb36bdf0e5929ecc7e0e5",
        requested_code_changes=True,
    )
    assert normalized["permitted_operations"] == sorted(
        ["inspect", "modify", "validate", "commit", "mechanical_reconcile", "push"]
    )


def test_missing_and_ambiguous_boundaries_fail_closed() -> None:
    arguments = {
        "repository_key": "acp-enterprise",
        "expected_branch": "customer-management-v1",
        "expected_head": "9c2b114cb658be0454bbb36bdf0e5929ecc7e0e5",
        "milestone_code": "TECH.1",
        "owning_workstream": "Field Service",
        "validation": (),
        "requested_code_changes": True,
    }
    with pytest.raises(ValueError, match="no approved machine-enforceable"):
        RoadmapService._execution_boundary(**arguments, starting_commit_evidence={})
    with pytest.raises(ValueError, match="invalid machine-enforceable"):
        RoadmapService._execution_boundary(
            **arguments,
            starting_commit_evidence={
                "execution_boundary": [{"boundary_id": "TECH.1"}]
            },
        )


def test_mismatched_boundary_identity_fails_closed() -> None:
    evidence, _ = _tech_contract()
    boundary = deepcopy(evidence["execution_boundary"])
    assert isinstance(boundary, dict)
    boundary["boundary_id"] = "TECH.2"
    boundary["fingerprint"] = manifest_fingerprint(
        {key: value for key, value in boundary.items() if key != "fingerprint"}
    )
    ExecutionBoundaryDefinition.model_validate(boundary)
    with pytest.raises(ValueError, match="does not match"):
        RoadmapService._execution_boundary(
            repository_key="acp-enterprise",
            expected_branch="customer-management-v1",
            expected_head="9c2b114cb658be0454bbb36bdf0e5929ecc7e0e5",
            milestone_code="TECH.1",
            owning_workstream="Field Service",
            starting_commit_evidence={"execution_boundary": boundary},
            validation=(),
            requested_code_changes=True,
        )


def test_tech_boundary_rejects_path_expansion_and_prohibited_operation() -> None:
    _, resolved = _tech_contract()
    boundary = ProviderBoundary(
        allowed_repository=str(resolved["allowed_repository"]),
        allowed_branch=str(resolved["allowed_branch"]),
        expected_head=str(resolved["expected_head"]),
        allowed_paths=tuple(resolved["allowed_paths"]),  # type: ignore[arg-type]
        forbidden_paths=tuple(resolved["forbidden_paths"]),  # type: ignore[arg-type]
        permitted_operations=tuple(resolved["permitted_operations"]),  # type: ignore[arg-type]
        validation_requirements=tuple(resolved["validation_requirements"]),  # type: ignore[arg-type]
    )
    enforce_changed_paths(
        boundary,
        ("frontend/src/features/technician/TechnicianShell.tsx",),
    )
    with pytest.raises(BoundaryViolation, match="Changed path is forbidden"):
        enforce_changed_paths(boundary, ("backend/app/jobs/service.py",))

    invalid = dict(resolved)
    invalid["permitted_operations"] = [
        "inspect",
        "modify",
        "validate",
        "commit",
        "push",
        "deploy",
    ]
    with pytest.raises(EngineeringCommandValidationError, match="not permitted"):
        EngineeringControlService._normalize_execution_boundary(
            invalid,
            repository_key="acp-enterprise",
            expected_branch="customer-management-v1",
            expected_head="9c2b114cb658be0454bbb36bdf0e5929ecc7e0e5",
            requested_code_changes=True,
        )
