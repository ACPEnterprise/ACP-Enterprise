from app.platform.permissions.catalog import (
    PermissionCatalog,
    PermissionDefinition,
    PermissionScope,
)
from app.platform.permissions.verification import (
    AuthorizationMatrixFindingCode,
    AuthorizationMatrixInput,
    AuthorizationMatrixReport,
    BackendAuthorizationRequirement,
    FrontendAuthorizationExposure,
    RolePermissionReference,
    verify_authorization_matrix,
)

READ = PermissionDefinition(
    code="COMPANY_WORK_READ",
    name="Work Read",
    resource="work",
    action="read",
    scope=PermissionScope.COMPANY,
)


def requirement(
    *,
    code: str = READ.code,
    points: tuple[str, ...] = ("app.work.router:list_work",),
    scope: PermissionScope = PermissionScope.COMPANY,
    branch_scoped: bool = True,
) -> BackendAuthorizationRequirement:
    return BackendAuthorizationRequirement(
        capability="work.read",
        permission_code=code,
        scope=scope,
        enforcement_points=points,
        branch_scoped=branch_scoped,
    )


def finding_codes(
    report: AuthorizationMatrixReport,
) -> set[AuthorizationMatrixFindingCode]:
    return {finding.code for finding in report.findings}


def test_known_valid_authorization_matrix_passes() -> None:
    report = verify_authorization_matrix(
        PermissionCatalog((READ,)),
        AuthorizationMatrixInput(
            backend_requirements=(requirement(),),
            frontend_exposures=(
                FrontendAuthorizationExposure(
                    "work.read", READ.code, "WorkRoute:read"
                ),
            ),
            role_permissions=(RolePermissionReference("DISPATCHER", READ.code),),
        ),
    )

    assert report.passed
    assert report.findings == ()


def test_unknown_permission_fails_closed() -> None:
    report = verify_authorization_matrix(
        PermissionCatalog((READ,)),
        AuthorizationMatrixInput((requirement(code="COMPANY_UNKNOWN"),)),
    )
    assert AuthorizationMatrixFindingCode.UNKNOWN_PERMISSION in finding_codes(report)


def test_missing_backend_enforcement_is_detected() -> None:
    report = verify_authorization_matrix(
        PermissionCatalog((READ,)), AuthorizationMatrixInput((requirement(points=()),))
    )
    assert AuthorizationMatrixFindingCode.MISSING_BACKEND_ENFORCEMENT in finding_codes(
        report
    )


def test_frontend_backend_mismatch_is_detected() -> None:
    manage = PermissionDefinition(
        "COMPANY_WORK_MANAGE",
        "Work Manage",
        "work",
        "manage",
        PermissionScope.COMPANY,
    )
    report = verify_authorization_matrix(
        PermissionCatalog((READ, manage)),
        AuthorizationMatrixInput(
            backend_requirements=(requirement(),),
            frontend_exposures=(
                FrontendAuthorizationExposure("work.read", manage.code, "WorkRoute"),
            ),
        ),
    )
    assert AuthorizationMatrixFindingCode.FRONTEND_BACKEND_MISMATCH in finding_codes(
        report
    )


def test_frontend_exposure_without_backend_authority_is_detected() -> None:
    report = verify_authorization_matrix(
        PermissionCatalog((READ,)),
        AuthorizationMatrixInput(
            frontend_exposures=(
                FrontendAuthorizationExposure("work.read", READ.code, "WorkRoute"),
            )
        ),
    )
    assert AuthorizationMatrixFindingCode.FRONTEND_BACKEND_MISMATCH in finding_codes(
        report
    )


def test_invalid_role_permission_reference_is_detected() -> None:
    report = verify_authorization_matrix(
        PermissionCatalog((READ,)),
        AuthorizationMatrixInput(
            backend_requirements=(requirement(),),
            role_permissions=(RolePermissionReference("BROKEN", "COMPANY_UNKNOWN"),),
        ),
    )
    assert AuthorizationMatrixFindingCode.INVALID_ROLE_PERMISSION in finding_codes(report)


def test_company_branch_scope_mismatch_is_detected() -> None:
    platform_read = PermissionDefinition(
        "PLATFORM_WORK_READ",
        "Platform Work Read",
        "work",
        "read",
        PermissionScope.PLATFORM,
    )
    report = verify_authorization_matrix(
        PermissionCatalog((platform_read,)),
        AuthorizationMatrixInput(
            (requirement(code=platform_read.code, scope=PermissionScope.PLATFORM),)
        ),
    )
    assert AuthorizationMatrixFindingCode.SCOPE_MISMATCH in finding_codes(report)


def test_identical_authority_has_identical_output() -> None:
    matrix = AuthorizationMatrixInput((requirement(),))
    first = verify_authorization_matrix(PermissionCatalog((READ,)), matrix)
    second = verify_authorization_matrix(PermissionCatalog((READ,)), matrix)
    assert first == second
    assert first.as_dict() == second.as_dict()


def test_fingerprint_binds_exact_enforcement_evidence() -> None:
    first = verify_authorization_matrix(
        PermissionCatalog((READ,)), AuthorizationMatrixInput((requirement(),))
    )
    second = verify_authorization_matrix(
        PermissionCatalog((READ,)),
        AuthorizationMatrixInput(
            (requirement(points=("app.work.router:get_work",)),)
        ),
    )
    assert first.fingerprint != second.fingerprint


def test_verification_does_not_mutate_inputs() -> None:
    requirements = (requirement(),)
    matrix = AuthorizationMatrixInput(requirements)
    verify_authorization_matrix(PermissionCatalog((READ,)), matrix)
    assert matrix.backend_requirements is requirements


def test_catalog_permission_without_enforcement_is_detected() -> None:
    report = verify_authorization_matrix(
        PermissionCatalog((READ,)), AuthorizationMatrixInput(())
    )
    assert AuthorizationMatrixFindingCode.PERMISSION_NEVER_ENFORCED in finding_codes(
        report
    )
