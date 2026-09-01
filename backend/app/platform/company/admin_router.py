from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.company.admin_schemas import (
    AllBranchAccessRequest,
    AssignmentResponse,
    CanonicalRoleSyncApplyRequest,
    CanonicalRoleSyncItemResponse,
    CanonicalRoleSyncPlanResponse,
    CanonicalRoleSyncResultResponse,
    MembershipCreateRequest,
    MembershipResponse,
    MutationResponse,
    PermissionCatalogResponse,
    RoleCreateRequest,
    RoleResponse,
    StatusUpdateRequest,
)
from app.platform.company.admin_service import (
    AccessPolicyAdministrationError,
    AccessPolicyConflictError,
    AccessPolicyNotFoundError,
    company_administration_service,
)
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AdministrationPermission
from app.platform.permissions.dependencies import require_permission
from app.platform.permissions.role_sync import (
    CanonicalRoleSyncConflict,
    RoleSyncPlan,
    canonical_role_sync_service,
)
from app.platform.reliability.correlation import current_correlation_id
from app.platform.reliability.failures import ClientRecovery, FailureCode, SafeFailure

router = APIRouter(prefix="/api/v1/company-admin", tags=["Company Administration"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
MembershipReadContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(AdministrationPermission.MEMBERSHIP_READ)),
]
MembershipManageContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(AdministrationPermission.MEMBERSHIP_MANAGE)),
]
BranchManageContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(AdministrationPermission.BRANCH_ACCESS_MANAGE)),
]
RoleReadContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(AdministrationPermission.ROLE_READ)),
]
RoleManageContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(AdministrationPermission.ROLE_MANAGE)),
]
PermissionManageContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(AdministrationPermission.PERMISSION_MANAGE)),
]


def canonical_role_plan_response(plan: RoleSyncPlan) -> CanonicalRoleSyncPlanResponse:
    return CanonicalRoleSyncPlanResponse(
        company_id=plan.company_id,
        plan_digest=plan.digest,
        safe_to_apply=plan.safe_to_apply,
        items=tuple(
            CanonicalRoleSyncItemResponse(
                code=item.code,
                classification=item.classification.value,
                missing_permissions=item.missing_permissions,
                metadata_update_required=item.metadata_update_required,
            )
            for item in plan.items
        ),
    )


def translate_admin_error(error: AccessPolicyAdministrationError) -> HTTPException:
    if isinstance(error, AccessPolicyNotFoundError):
        failure = SafeFailure(
            FailureCode.NOT_FOUND,
            "Access-policy resource was not found.",
            ClientRecovery.TERMINAL_FAILURE,
            current_correlation_id(),
        )
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=failure.detail(),
        )
    if isinstance(error, AccessPolicyConflictError):
        failure = SafeFailure(
            FailureCode.RESOURCE_STATE_CONFLICT,
            "Access-policy operation conflicts with current authority.",
            ClientRecovery.RETRY_AFTER_REFRESH,
            current_correlation_id(),
        )
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=failure.detail(),
        )
    failure = SafeFailure(
        FailureCode.VALIDATION,
        "Access-policy request requires correction.",
        ClientRecovery.USER_CORRECTION_REQUIRED,
        current_correlation_id(),
    )
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=failure.detail(),
    )


def translate_canonical_role_sync_error(
    error: CanonicalRoleSyncConflict,
) -> HTTPException:
    del error
    failure = SafeFailure(
        FailureCode.RESOURCE_STATE_CONFLICT,
        "Canonical role reconciliation conflicts with current authority.",
        ClientRecovery.RETRY_AFTER_REFRESH,
        current_correlation_id(),
    )
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=failure.detail(),
    )


@router.get("/memberships", response_model=list[MembershipResponse])
async def list_memberships(
    context: MembershipReadContext,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[MembershipResponse]:
    records = await company_administration_service.list_memberships(
        session, context=context, limit=limit, offset=offset
    )
    return [MembershipResponse.model_validate(record) for record in records]


@router.post(
    "/memberships",
    response_model=MembershipResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_membership(
    data: MembershipCreateRequest,
    context: MembershipManageContext,
    session: DatabaseSession,
) -> MembershipResponse:
    try:
        record = await company_administration_service.create_membership(
            session,
            context=context,
            user_id=data.user_id,
            status=data.status,
            default_branch_id=data.default_branch_id,
            has_all_branch_access=data.has_all_branch_access,
        )
    except AccessPolicyAdministrationError as error:
        raise translate_admin_error(error) from error
    return MembershipResponse.model_validate(record)


@router.patch(
    "/memberships/{membership_id}/status",
    response_model=MembershipResponse,
)
async def set_membership_status(
    membership_id: UUID,
    data: StatusUpdateRequest,
    context: MembershipManageContext,
    session: DatabaseSession,
) -> MembershipResponse:
    try:
        record = await company_administration_service.set_membership_status(
            session,
            context=context,
            membership_id=membership_id,
            status=data.status,
        )
    except AccessPolicyAdministrationError as error:
        raise translate_admin_error(error) from error
    return MembershipResponse.model_validate(record)


@router.put(
    "/memberships/{membership_id}/branches/{branch_id}",
    response_model=AssignmentResponse,
)
async def add_branch_access(
    membership_id: UUID,
    branch_id: UUID,
    context: BranchManageContext,
    session: DatabaseSession,
) -> AssignmentResponse:
    try:
        record = await company_administration_service.add_branch_access(
            session,
            context=context,
            membership_id=membership_id,
            branch_id=branch_id,
        )
    except AccessPolicyAdministrationError as error:
        raise translate_admin_error(error) from error
    return AssignmentResponse(id=record.id)


@router.delete(
    "/memberships/{membership_id}/branches/{branch_id}",
    response_model=MutationResponse,
)
async def remove_branch_access(
    membership_id: UUID,
    branch_id: UUID,
    context: BranchManageContext,
    session: DatabaseSession,
) -> MutationResponse:
    try:
        changed = await company_administration_service.remove_branch_access(
            session,
            context=context,
            membership_id=membership_id,
            branch_id=branch_id,
        )
    except AccessPolicyAdministrationError as error:
        raise translate_admin_error(error) from error
    return MutationResponse(changed=changed)


@router.put(
    "/memberships/{membership_id}/all-branch-access",
    response_model=MembershipResponse,
)
async def set_all_branch_access(
    membership_id: UUID,
    data: AllBranchAccessRequest,
    context: BranchManageContext,
    session: DatabaseSession,
) -> MembershipResponse:
    try:
        record = await company_administration_service.set_all_branch_access(
            session,
            context=context,
            membership_id=membership_id,
            enabled=data.enabled,
        )
    except AccessPolicyAdministrationError as error:
        raise translate_admin_error(error) from error
    return MembershipResponse.model_validate(record)


@router.get("/roles", response_model=list[RoleResponse])
async def list_roles(
    context: RoleReadContext,
    session: DatabaseSession,
) -> list[RoleResponse]:
    records = await company_administration_service.list_roles(session, context=context)
    return [RoleResponse.model_validate(record) for record in records]


@router.get(
    "/canonical-roles/reconciliation",
    response_model=CanonicalRoleSyncPlanResponse,
)
async def preview_canonical_role_reconciliation(
    context: RoleReadContext,
    session: DatabaseSession,
) -> CanonicalRoleSyncPlanResponse:
    plan = await canonical_role_sync_service.plan(
        session, company_id=context.company.id
    )
    return canonical_role_plan_response(plan)


@router.post(
    "/canonical-roles/reconciliation/apply",
    response_model=CanonicalRoleSyncResultResponse,
)
async def apply_canonical_role_reconciliation(
    data: CanonicalRoleSyncApplyRequest,
    context: RoleManageContext,
    session: DatabaseSession,
) -> CanonicalRoleSyncResultResponse:
    try:
        result = await canonical_role_sync_service.apply(
            session,
            context=context,
            expected_plan_digest=data.expected_plan_digest,
        )
    except CanonicalRoleSyncConflict as error:
        raise translate_canonical_role_sync_error(error) from error
    return CanonicalRoleSyncResultResponse(
        plan=canonical_role_plan_response(result.plan),
        roles_created=result.roles_created,
        permissions_added=result.permissions_added,
        metadata_restored=result.metadata_restored,
        authorization_users_advanced=result.authorization_users_advanced,
    )


@router.get("/permissions", response_model=list[PermissionCatalogResponse])
async def list_permission_catalog(
    context: RoleReadContext,
    session: DatabaseSession,
    role_id: UUID | None = None,
) -> list[PermissionCatalogResponse]:
    try:
        records = await company_administration_service.list_permission_catalog(
            session, context=context, role_id=role_id
        )
    except AccessPolicyAdministrationError as error:
        raise translate_admin_error(error) from error
    return [PermissionCatalogResponse.model_validate(record) for record in records]


@router.post("/roles", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    data: RoleCreateRequest,
    context: RoleManageContext,
    session: DatabaseSession,
) -> RoleResponse:
    try:
        record = await company_administration_service.create_role(
            session,
            context=context,
            code=data.code,
            name=data.name,
            description=data.description,
            is_system=False,
        )
    except AccessPolicyAdministrationError as error:
        raise translate_admin_error(error) from error
    return RoleResponse.model_validate(record)


@router.patch("/roles/{role_id}/status", response_model=RoleResponse)
async def set_role_status(
    role_id: UUID,
    data: StatusUpdateRequest,
    context: RoleManageContext,
    session: DatabaseSession,
) -> RoleResponse:
    try:
        record = await company_administration_service.set_role_status(
            session,
            context=context,
            role_id=role_id,
            status=data.status,
        )
    except AccessPolicyAdministrationError as error:
        raise translate_admin_error(error) from error
    return RoleResponse.model_validate(record)


@router.put(
    "/memberships/{membership_id}/roles/{role_id}",
    response_model=AssignmentResponse,
)
async def assign_role(
    membership_id: UUID,
    role_id: UUID,
    context: RoleManageContext,
    session: DatabaseSession,
) -> AssignmentResponse:
    try:
        record = await company_administration_service.assign_role(
            session,
            context=context,
            membership_id=membership_id,
            role_id=role_id,
        )
    except AccessPolicyAdministrationError as error:
        raise translate_admin_error(error) from error
    return AssignmentResponse(id=record.id)


@router.delete(
    "/memberships/{membership_id}/roles/{role_id}",
    response_model=MutationResponse,
)
async def revoke_role(
    membership_id: UUID,
    role_id: UUID,
    context: RoleManageContext,
    session: DatabaseSession,
) -> MutationResponse:
    try:
        changed = await company_administration_service.revoke_role(
            session,
            context=context,
            membership_id=membership_id,
            role_id=role_id,
        )
    except AccessPolicyAdministrationError as error:
        raise translate_admin_error(error) from error
    return MutationResponse(changed=changed)


@router.put(
    "/roles/{role_id}/permissions/{permission_id}",
    response_model=AssignmentResponse,
)
async def assign_permission(
    role_id: UUID,
    permission_id: UUID,
    context: PermissionManageContext,
    session: DatabaseSession,
) -> AssignmentResponse:
    try:
        record = await company_administration_service.assign_permission(
            session,
            context=context,
            role_id=role_id,
            permission_id=permission_id,
        )
    except AccessPolicyAdministrationError as error:
        raise translate_admin_error(error) from error
    return AssignmentResponse(id=record.id)


@router.delete(
    "/roles/{role_id}/permissions/{permission_id}",
    response_model=MutationResponse,
)
async def remove_permission(
    role_id: UUID,
    permission_id: UUID,
    context: PermissionManageContext,
    session: DatabaseSession,
) -> MutationResponse:
    try:
        changed = await company_administration_service.remove_permission(
            session,
            context=context,
            role_id=role_id,
            permission_id=permission_id,
        )
    except AccessPolicyAdministrationError as error:
        raise translate_admin_error(error) from error
    return MutationResponse(changed=changed)
