from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AdministrationPermission
from app.platform.permissions.dependencies import require_permission
from app.qbo_source.evidence import ProtectedFilesystemEvidenceStore
from app.qbo_source.runtime import (
    get_production_oauth_runtime,
    get_sandbox_oauth_runtime,
)

from .product_projection import build_migration_product_projection

router = APIRouter(prefix="/api/v1/migration", tags=["Migration Administration"])
Review = Annotated[
    AuthorizationContext,
    Depends(require_permission(AdministrationPermission.COMPANY_ADMINISTER)),
]


@router.get("/readiness", name="migration-readiness-review")
async def migration_readiness_review(context: Review) -> JSONResponse:
    branch = context.active_branch
    try:
        connected = get_sandbox_oauth_runtime().connection_state() == "connected"
    except Exception:  # noqa: BLE001 - never expose protected runtime failures
        connected = False
    production_connected = False
    production_snapshot: dict[str, object] | None = None
    try:
        production_connected = (
            get_production_oauth_runtime().connection_state() == "connected"
        )
        if production_connected and settings.qbo_production_evidence_root:
            production_snapshot = ProtectedFilesystemEvidenceStore(
                root=Path(settings.qbo_production_evidence_root),
                repository_root=Path(settings.qbo_repository_root),
                bounded_snapshot=True,
            ).latest_bounded_snapshot_summary()
    except Exception:  # noqa: BLE001 - safe unavailable projection
        production_connected = False
        production_snapshot = None
    projection = build_migration_product_projection(
        company_id=str(context.company.id),
        branch_id=str(branch.id) if branch is not None else None,
        qbo_sandbox_connected=connected,
        qbo_production_connected=production_connected,
        qbo_production_snapshot=production_snapshot,
    )
    return JSONResponse(
        content=projection, headers={"Cache-Control": "private, no-store"}
    )
