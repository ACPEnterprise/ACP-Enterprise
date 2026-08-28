import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum

from app.platform.permissions.catalog import (
    PermissionCatalog,
    PermissionCatalogError,
    PermissionScope,
)


class AuthorizationMatrixFindingCode(StrEnum):
    INVALID_CATALOG = "invalid_catalog"
    UNKNOWN_PERMISSION = "unknown_permission"
    PERMISSION_NEVER_ENFORCED = "permission_never_enforced"
    MISSING_BACKEND_ENFORCEMENT = "missing_backend_enforcement"
    FRONTEND_BACKEND_MISMATCH = "frontend_backend_mismatch"
    INVALID_ROLE_PERMISSION = "invalid_role_permission"
    SCOPE_MISMATCH = "scope_mismatch"
    CONTRADICTORY_CAPABILITY = "contradictory_capability"


@dataclass(frozen=True)
class BackendAuthorizationRequirement:
    capability: str
    permission_code: str
    scope: PermissionScope
    enforcement_points: tuple[str, ...]
    branch_scoped: bool = False


@dataclass(frozen=True)
class FrontendAuthorizationExposure:
    capability: str
    permission_code: str
    exposure_point: str


@dataclass(frozen=True)
class RolePermissionReference:
    role_code: str
    permission_code: str


@dataclass(frozen=True)
class AuthorizationMatrixInput:
    backend_requirements: tuple[BackendAuthorizationRequirement, ...] = ()
    frontend_exposures: tuple[FrontendAuthorizationExposure, ...] = ()
    role_permissions: tuple[RolePermissionReference, ...] = ()


@dataclass(frozen=True, order=True)
class AuthorizationMatrixFinding:
    code: AuthorizationMatrixFindingCode
    subject: str
    detail: str


@dataclass(frozen=True)
class AuthorizationMatrixReport:
    catalog_codes: tuple[str, ...]
    backend_requirements: tuple[BackendAuthorizationRequirement, ...]
    frontend_exposures: tuple[FrontendAuthorizationExposure, ...]
    role_permissions: tuple[RolePermissionReference, ...]
    findings: tuple[AuthorizationMatrixFinding, ...]
    fingerprint: str

    @property
    def passed(self) -> bool:
        return not self.findings

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "catalog_codes": list(self.catalog_codes),
            "backend_requirements": [
                _backend_payload(requirement)
                for requirement in self.backend_requirements
            ],
            "frontend_exposures": [
                _frontend_payload(exposure) for exposure in self.frontend_exposures
            ],
            "role_permissions": [
                _role_payload(reference) for reference in self.role_permissions
            ],
            "findings": [
                {
                    "code": finding.code.value,
                    "subject": finding.subject,
                    "detail": finding.detail,
                }
                for finding in self.findings
            ],
            "fingerprint": self.fingerprint,
        }


def verify_authorization_matrix(
    catalog: PermissionCatalog,
    matrix: AuthorizationMatrixInput,
) -> AuthorizationMatrixReport:
    """Return deterministic, mutation-free authorization consistency evidence."""
    findings: set[AuthorizationMatrixFinding] = set()
    try:
        catalog.validate()
    except PermissionCatalogError as exc:
        findings.add(
            AuthorizationMatrixFinding(
                AuthorizationMatrixFindingCode.INVALID_CATALOG,
                "permission_catalog",
                str(exc),
            )
        )

    definitions = {definition.code: definition for definition in catalog.definitions}
    backend_by_capability: dict[str, set[str]] = {}
    enforced_codes: set[str] = set()

    for requirement in matrix.backend_requirements:
        backend_by_capability.setdefault(requirement.capability, set()).add(
            requirement.permission_code
        )
        definition = definitions.get(requirement.permission_code)
        if definition is None:
            findings.add(
                AuthorizationMatrixFinding(
                    AuthorizationMatrixFindingCode.UNKNOWN_PERMISSION,
                    requirement.capability,
                    f"backend references {requirement.permission_code}",
                )
            )
            continue
        if not requirement.enforcement_points:
            findings.add(
                AuthorizationMatrixFinding(
                    AuthorizationMatrixFindingCode.MISSING_BACKEND_ENFORCEMENT,
                    requirement.capability,
                    f"{requirement.permission_code} has no enforcement point",
                )
            )
        else:
            enforced_codes.add(requirement.permission_code)
        if definition.scope is not requirement.scope or (
            requirement.branch_scoped and definition.scope is PermissionScope.PLATFORM
        ):
            findings.add(
                AuthorizationMatrixFinding(
                    AuthorizationMatrixFindingCode.SCOPE_MISMATCH,
                    requirement.capability,
                    f"{requirement.permission_code} catalog={definition.scope.value} "
                    f"requirement={requirement.scope.value} branch={requirement.branch_scoped}",
                )
            )

    for capability, codes in backend_by_capability.items():
        if len(codes) > 1:
            findings.add(
                AuthorizationMatrixFinding(
                    AuthorizationMatrixFindingCode.CONTRADICTORY_CAPABILITY,
                    capability,
                    f"backend declares {','.join(sorted(codes))}",
                )
            )

    for exposure in matrix.frontend_exposures:
        if exposure.permission_code not in definitions:
            findings.add(
                AuthorizationMatrixFinding(
                    AuthorizationMatrixFindingCode.UNKNOWN_PERMISSION,
                    exposure.capability,
                    f"frontend references {exposure.permission_code}",
                )
            )
            continue
        backend_codes = backend_by_capability.get(exposure.capability, set())
        if exposure.permission_code not in backend_codes:
            findings.add(
                AuthorizationMatrixFinding(
                    AuthorizationMatrixFindingCode.FRONTEND_BACKEND_MISMATCH,
                    exposure.capability,
                    f"frontend={exposure.permission_code} "
                    f"backend={','.join(sorted(backend_codes))}",
                )
            )

    for reference in matrix.role_permissions:
        if reference.permission_code not in definitions:
            findings.add(
                AuthorizationMatrixFinding(
                    AuthorizationMatrixFindingCode.INVALID_ROLE_PERMISSION,
                    reference.role_code,
                    f"role references {reference.permission_code}",
                )
            )

    for code in definitions.keys() - enforced_codes:
        findings.add(
            AuthorizationMatrixFinding(
                AuthorizationMatrixFindingCode.PERMISSION_NEVER_ENFORCED,
                code,
                "catalog permission has no declared backend enforcement",
            )
        )

    ordered_codes = tuple(sorted(definitions))
    ordered_backend = tuple(
        sorted(
            matrix.backend_requirements,
            key=lambda item: (
                item.capability,
                item.permission_code,
                item.scope.value,
                item.branch_scoped,
                item.enforcement_points,
            ),
        )
    )
    ordered_frontend = tuple(
        sorted(
            matrix.frontend_exposures,
            key=lambda item: (
                item.capability,
                item.permission_code,
                item.exposure_point,
            ),
        )
    )
    ordered_roles = tuple(
        sorted(
            matrix.role_permissions,
            key=lambda item: (item.role_code, item.permission_code),
        )
    )
    ordered_findings = tuple(sorted(findings))
    payload = {
        "schema_version": "1.0",
        "catalog_codes": list(ordered_codes),
        "backend_requirements": [
            _backend_payload(requirement) for requirement in ordered_backend
        ],
        "frontend_exposures": [
            _frontend_payload(exposure) for exposure in ordered_frontend
        ],
        "role_permissions": [_role_payload(reference) for reference in ordered_roles],
        "findings": [
            {
                "code": finding.code.value,
                "subject": finding.subject,
                "detail": finding.detail,
            }
            for finding in ordered_findings
        ],
    }
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return AuthorizationMatrixReport(
        ordered_codes,
        ordered_backend,
        ordered_frontend,
        ordered_roles,
        ordered_findings,
        fingerprint,
    )


def _backend_payload(
    requirement: BackendAuthorizationRequirement,
) -> dict[str, object]:
    return {
        "capability": requirement.capability,
        "permission_code": requirement.permission_code,
        "scope": requirement.scope.value,
        "enforcement_points": sorted(requirement.enforcement_points),
        "branch_scoped": requirement.branch_scoped,
    }


def _frontend_payload(exposure: FrontendAuthorizationExposure) -> dict[str, str]:
    return {
        "capability": exposure.capability,
        "permission_code": exposure.permission_code,
        "exposure_point": exposure.exposure_point,
    }


def _role_payload(reference: RolePermissionReference) -> dict[str, str]:
    return {
        "role_code": reference.role_code,
        "permission_code": reference.permission_code,
    }
