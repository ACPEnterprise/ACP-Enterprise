from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AdministrationPermission
from app.platform.permissions.dependencies import require_permission
from app.qbo_source.runtime import get_sandbox_oauth_runtime

from .product_projection import build_migration_product_projection

router = APIRouter(prefix="/api/v1/migration", tags=["Migration Administration"])
Review = Annotated[
    AuthorizationContext,
    Depends(require_permission(AdministrationPermission.COMPANY_ADMINISTER)),
]


@router.get("/readiness", name="migration-readiness-review")
async def migration_readiness_review(context: Review) -> JSONResponse:
    branch = context.active_branch
    if branch is None:
        return JSONResponse(
            status_code=409,
            content={"status": "blocked", "safe_failure_code": "branch_required"},
        )
    try:
        connected = get_sandbox_oauth_runtime().connection_state() == "connected"
    except Exception:  # noqa: BLE001 - never expose protected runtime failures
        connected = False
    projection = build_migration_product_projection(
        company_id=str(context.company.id),
        branch_id=str(branch.id),
        qbo_sandbox_connected=connected,
    )
    return JSONResponse(
        content=projection, headers={"Cache-Control": "private, no-store"}
    )
