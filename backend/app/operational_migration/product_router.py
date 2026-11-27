from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.customer_migration.models import CustomerSourceIdentity
from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import (
    AdministrationPermission,
    CustomerPermission,
    EstimatePermission,
    InvoicePermission,
    PaymentPermission,
)
from app.platform.permissions.dependencies import require_permission
from app.qbo_source.evidence import ProtectedFilesystemEvidenceStore
from app.qbo_source.runtime import (
    get_production_oauth_runtime,
    get_sandbox_oauth_runtime,
)

from .hcp_customer_source_history import (
    HcpCustomerSourceHistoryError,
    project_customer_source_history,
    search_customer_source_history,
)
from .product_projection import build_migration_product_projection

router = APIRouter(prefix="/api/v1/migration", tags=["Migration Administration"])
Review = Annotated[
    AuthorizationContext,
    Depends(require_permission(AdministrationPermission.COMPANY_ADMINISTER)),
]
CustomerRead = Annotated[
    AuthorizationContext, Depends(require_permission(CustomerPermission.READ))
]
EstimateRead = Annotated[
    AuthorizationContext, Depends(require_permission(EstimatePermission.READ))
]
InvoiceRead = Annotated[
    AuthorizationContext, Depends(require_permission(InvoicePermission.READ))
]
PaymentRead = Annotated[
    AuthorizationContext, Depends(require_permission(PaymentPermission.READ))
]
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]


def _history_unavailable(status_code: int = status.HTTP_404_NOT_FOUND) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": "Historical source evidence is not available."},
        headers={"Cache-Control": "private, no-store"},
    )


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


@router.get(
    "/source-history/customers/{customer_id}",
    name="hcp-customer-source-history",
)
async def hcp_customer_source_history(
    customer_id: UUID,
    context: CustomerRead,
    estimate_context: EstimateRead,
    invoice_context: InvoiceRead,
    payment_context: PaymentRead,
    session: DatabaseSession,
) -> JSONResponse:
    """Expose sealed HCP evidence linked by an exact admitted Customer identity."""
    if not settings.hcp_source4_evidence_root:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "Historical source evidence is not available."},
            headers={"Cache-Control": "private, no-store"},
        )
    if not (
        context.company.id
        == estimate_context.company.id
        == invoice_context.company.id
        == payment_context.company.id
    ):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Historical source scope does not match."},
            headers={"Cache-Control": "private, no-store"},
        )
    identities = tuple(
        (
            await session.scalars(
                select(CustomerSourceIdentity).where(
                    CustomerSourceIdentity.company_id == context.company.id,
                    CustomerSourceIdentity.customer_id == customer_id,
                    CustomerSourceIdentity.branch_id.in_(context.authorized_branch_ids),
                    CustomerSourceIdentity.source_system.in_(
                        ("housecall_pro", "housecall_pro_source4")
                    ),
                )
            )
        ).all()
    )
    source4_ids = {
        identity.source_customer_id
        for identity in identities
        if identity.source_system == "housecall_pro_source4"
    }
    legacy_ids = {
        identity.source_customer_id
        for identity in identities
        if identity.source_system == "housecall_pro"
    }
    # A bridged Customer legitimately retains both its old numeric identity and
    # the current opaque provider identity.  Product history must use SOURCE.4;
    # the predecessor remains audit evidence and is never a second Customer.
    source_ids = source4_ids or legacy_ids
    if len(source_ids) != 1:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "Exact HCP Customer source identity is unavailable."},
            headers={"Cache-Control": "private, no-store"},
        )
    try:
        result = project_customer_source_history(
            Path(settings.hcp_source4_evidence_root),
            source_customer_id=next(iter(source_ids)),
            attachment_root=(
                Path(settings.hcp_historical_attachment_root)
                if settings.hcp_historical_attachment_root
                else None
            ),
        )
    except (OSError, ValueError, HcpCustomerSourceHistoryError):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Historical source evidence is unavailable."},
            headers={"Cache-Control": "private, no-store"},
        )
    return JSONResponse(content=result, headers={"Cache-Control": "private, no-store"})


@router.get("/source-history/customers", name="hcp-historical-customer-search")
async def hcp_historical_customer_search(
    query: str,
    context: CustomerRead,
    limit: int = 20,
) -> JSONResponse:
    """Search sealed HCP history independently of native Customer admission."""
    del context
    if not settings.hcp_source4_evidence_root:
        return _history_unavailable()
    try:
        result = search_customer_source_history(
            Path(settings.hcp_source4_evidence_root), query=query, limit=limit
        )
    except HcpCustomerSourceHistoryError as error:
        code = (
            status.HTTP_422_UNPROCESSABLE_CONTENT
            if str(error) in {"search_query_too_short", "search_limit_invalid"}
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        return _history_unavailable(code)
    except (OSError, ValueError):
        return _history_unavailable(status.HTTP_503_SERVICE_UNAVAILABLE)
    return JSONResponse(content=result, headers={"Cache-Control": "private, no-store"})


@router.get(
    "/source-history/customers/by-source/{source_customer_id}",
    name="hcp-customer-history-by-source",
)
async def hcp_customer_history_by_source(
    source_customer_id: str,
    context: CustomerRead,
    estimate_context: EstimateRead,
    invoice_context: InvoiceRead,
    payment_context: PaymentRead,
) -> JSONResponse:
    """Read one sealed historical Customer without creating a native identity."""
    if not settings.hcp_source4_evidence_root:
        return _history_unavailable()
    if not (
        context.company.id
        == estimate_context.company.id
        == invoice_context.company.id
        == payment_context.company.id
    ):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Historical source scope does not match."},
            headers={"Cache-Control": "private, no-store"},
        )
    try:
        result = project_customer_source_history(
            Path(settings.hcp_source4_evidence_root),
            source_customer_id=source_customer_id,
            attachment_root=(
                Path(settings.hcp_historical_attachment_root)
                if settings.hcp_historical_attachment_root
                else None
            ),
        )
    except (OSError, ValueError, HcpCustomerSourceHistoryError):
        return _history_unavailable(status.HTTP_503_SERVICE_UNAVAILABLE)
    return JSONResponse(content=result, headers={"Cache-Control": "private, no-store"})


@router.get(
    "/source-history/attachments/{attachment_id}",
    name="hcp-source-history-attachment",
)
async def hcp_source_history_attachment(
    attachment_id: str,
    context: CustomerRead,
) -> Response:
    """Serve only a recovered, source-indexed body from protected custody."""
    del context
    if not settings.hcp_historical_attachment_root:
        return _history_unavailable()
    custody = Path(settings.hcp_historical_attachment_root).resolve()
    manifest_path = custody / "attachment-custody-manifest.json"
    if not manifest_path.is_file():
        return _history_unavailable(status.HTTP_503_SERVICE_UNAVAILABLE)
    try:
        manifest = json.loads(manifest_path.read_bytes())
        item = next(
            (
                row
                for row in manifest.get("attachments", [])
                if isinstance(row, dict) and row.get("source_id") == attachment_id
            ),
            None,
        )
        if not item or item.get("status") != "RECOVERED":
            return _history_unavailable()
        artifact = str(item.get("artifact") or "")
        body = (custody / artifact).resolve()
        if body.parent != custody or not body.is_file():
            return _history_unavailable(status.HTTP_503_SERVICE_UNAVAILABLE)
    except (OSError, ValueError, TypeError):
        return _history_unavailable(status.HTTP_503_SERVICE_UNAVAILABLE)
    return FileResponse(
        body,
        media_type=str(item.get("file_type") or "application/octet-stream"),
        filename=str(item.get("file_name") or artifact),
        headers={"Cache-Control": "private, no-store"},
    )
