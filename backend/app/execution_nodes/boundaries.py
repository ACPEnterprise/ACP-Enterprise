import fnmatch
import hashlib
import json
from pathlib import PurePosixPath

from .contracts import ProviderBoundary, ProviderExecutionRequest


class BoundaryViolation(RuntimeError):
    pass


MANDATORY_FORBIDDEN = frozenset({".git/**", ".env*", "**/.env*"})


def boundary_digest(boundary: ProviderBoundary) -> str:
    payload = {
        "allowed_repository": boundary.allowed_repository,
        "allowed_branch": boundary.allowed_branch,
        "expected_head": boundary.expected_head,
        "allowed_paths": sorted(set(boundary.allowed_paths)),
        "forbidden_paths": sorted(set(boundary.forbidden_paths)),
        "permitted_operations": sorted(set(boundary.permitted_operations)),
        "validation_requirements": sorted(set(boundary.validation_requirements)),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_request(request: ProviderExecutionRequest) -> None:
    boundary = request.boundary
    if (
        hashlib.sha256(request.instruction.encode()).hexdigest()
        != request.instruction_digest
    ):
        raise BoundaryViolation("Instruction digest mismatch.")
    if boundary_digest(boundary) != request.boundary_digest:
        raise BoundaryViolation("Execution boundary digest mismatch.")
    if not MANDATORY_FORBIDDEN <= set(boundary.forbidden_paths):
        raise BoundaryViolation("Mandatory forbidden paths are absent.")
    operations = set(boundary.permitted_operations)
    if request.repository_mutation_allowed:
        if request.execution_capability_profile != "code_change" or operations != {
            "inspect", "modify", "validate", "commit", "mechanical_reconcile", "push"
        }:
            raise BoundaryViolation("Code-changing authority is incomplete.")
    elif (
        request.execution_capability_profile != "inspect_validate_only"
        or operations != {"inspect", "validate"}
    ):
        raise BoundaryViolation("Read-only execution authority is invalid.")
    if not boundary.allowed_paths or not boundary.validation_requirements:
        raise BoundaryViolation("Paths and validation must be explicitly bounded.")
    for pattern in (*boundary.allowed_paths, *boundary.forbidden_paths):
        path = PurePosixPath(pattern)
        if path.is_absolute() or ".." in path.parts or "\\" in pattern:
            raise BoundaryViolation("Path boundary is unsafe.")


def enforce_changed_paths(boundary: ProviderBoundary, files: tuple[str, ...]) -> None:
    for path in files:
        if any(
            fnmatch.fnmatchcase(path, pattern) for pattern in boundary.forbidden_paths
        ):
            raise BoundaryViolation(f"Changed path is forbidden: {path}")
        if not any(
            fnmatch.fnmatchcase(path, pattern) for pattern in boundary.allowed_paths
        ):
            raise BoundaryViolation(
                f"Changed path is outside the approved boundary: {path}"
            )
