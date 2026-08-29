"""Fail-closed authority boundary for the isolated HCP rehearsal target."""

from __future__ import annotations

from uuid import UUID

from app.operational_migration.hcp_owner_disposition import NonProductionTarget
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import MigrationPermission

COMPANY_ID = UUID("3ddf07ce-0f44-4b67-a40f-fb0ec41bb7cd")
BRANCH_ID = UUID("887f413a-70dc-4ab1-98aa-8e84f4e7efd0")
ACTOR_ID = UUID("c427ebd1-7583-4c0d-9c54-55a0c1214174")
SOURCE4_SYSTEM = "housecall_pro_source4"


def require_sanctioned_context(context: AuthorizationContext) -> None:
    if (
        context.company.id != COMPANY_ID
        or context.user.id != ACTOR_ID
        or context.active_branch is None
        or context.active_branch.id != BRANCH_ID
        or not context.can_access_branch(BRANCH_ID)
        or not context.has_permission(MigrationPermission.EXECUTE_REHEARSAL)
    ):
        raise ValueError("sanctioned HCP rehearsal actor and scope are required")


def require_sanctioned_target(target: NonProductionTarget) -> str:
    digest = target.validate()
    if target.production_access_enabled or target.preview_access_enabled:
        raise ValueError("Preview and Production access must remain disabled")
    return digest
