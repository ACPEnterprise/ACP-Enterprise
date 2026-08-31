from dataclasses import dataclass

from app.platform.launch_controls import LAUNCH_ROLE_MATRIX


@dataclass(frozen=True, slots=True)
class CanonicalRoleDefinition:
    code: str
    name: str
    purpose: str
    permission_codes: frozenset[str]
    branch_access_required: bool


CANONICAL_ROLE_DEFINITIONS = tuple(
    CanonicalRoleDefinition(
        code=definition.code.value,
        name=definition.code.value.replace("_", " ").title(),
        purpose=definition.purpose,
        permission_codes=definition.permission_codes,
        branch_access_required=definition.branch_access_required,
    )
    for definition in LAUNCH_ROLE_MATRIX
)

CANONICAL_ROLE_BY_CODE = {item.code: item for item in CANONICAL_ROLE_DEFINITIONS}


def validate_canonical_roles(canonical_permission_codes: frozenset[str]) -> None:
    codes = [item.code for item in CANONICAL_ROLE_DEFINITIONS]
    if len(codes) != len(set(codes)):
        raise ValueError("Canonical role codes must be unique.")
    unknown = {
        permission
        for role in CANONICAL_ROLE_DEFINITIONS
        for permission in role.permission_codes
        if permission not in canonical_permission_codes
    }
    if unknown:
        raise ValueError(f"Canonical roles contain unknown permissions: {sorted(unknown)}")
