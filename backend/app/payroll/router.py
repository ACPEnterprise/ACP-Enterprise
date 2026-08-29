"""Authenticated employee and Payroll-admin pay-statement boundary."""

from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.dependencies import require_permission

from .contracts import PayrollAuthorizationError, PayrollConflictError
from .paystatement import PayrollPayStatementService, PayStatementView
from .paystatement_experience import (
    PayrollPayStatementExperienceService,
    ProtectedStatementStorage,
)
from .permissions import PayrollPermission

router = APIRouter(prefix="/api/v1/payroll", tags=["Payroll Pay Statements"])
Session = Annotated[AsyncSession, Depends(get_database_session)]
OwnRead = Annotated[
    AuthorizationContext,
    Depends(require_permission(PayrollPermission.STATEMENT_OWN_READ)),
]
AdminRead = Annotated[
    AuthorizationContext, Depends(require_permission(PayrollPermission.STATEMENT_READ))
]
Manage = Annotated[
    AuthorizationContext,
    Depends(require_permission(PayrollPermission.STATEMENT_MANAGE)),
]


class StatementMetadata(BaseModel):
    id: UUID
    pay_period_id: UUID
    version: int
    currency: str
    payment_status: str
    ytd_status: str
    lifecycle: str
    digest: str
    corrected: bool


def _metadata(value: PayStatementView) -> StatementMetadata:
    return StatementMetadata(
        id=value.id,
        pay_period_id=value.pay_period_id,
        version=value.version,
        currency=value.currency,
        payment_status=value.payment_status,
        ytd_status=value.ytd_status,
        lifecycle=value.lifecycle,
        digest=value.digest,
        corrected=value.version > 1,
    )


def _experience() -> PayrollPayStatementExperienceService:
    root = settings.payroll_paystatement_artifact_root
    if not root:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Protected pay-statement storage is not configured.",
        )
    return PayrollPayStatementExperienceService(ProtectedStatementStorage(Path(root)))


def _error(error: Exception) -> HTTPException:
    if isinstance(error, PayrollAuthorizationError):
        return HTTPException(status.HTTP_403_FORBIDDEN, "Pay statement access denied.")
    return HTTPException(status.HTTP_409_CONFLICT, str(error))


@router.get("/me/pay-statements", response_model=list[StatementMetadata])
async def list_own_pay_statements(
    context: OwnRead, session: Session
) -> list[StatementMetadata]:
    try:
        return [
            _metadata(value)
            for value in await PayrollPayStatementService().list_own(
                session, context=context
            )
        ]
    except (PayrollAuthorizationError, PayrollConflictError) as error:
        raise _error(error) from error


@router.get("/me/pay-statements/{statement_id}", response_model=StatementMetadata)
async def own_pay_statement(
    statement_id: UUID, context: OwnRead, session: Session
) -> StatementMetadata:
    try:
        return _metadata(
            await PayrollPayStatementService().own(
                session, context=context, statement_id=statement_id
            )
        )
    except (PayrollAuthorizationError, PayrollConflictError) as error:
        raise _error(error) from error


@router.get("/me/pay-statements/{statement_id}/artifact")
async def own_pay_statement_artifact(
    statement_id: UUID, context: OwnRead, session: Session
) -> Response:
    try:
        artifact, data = await _experience().own_artifact(
            session, context=context, statement_id=statement_id
        )
    except (PayrollAuthorizationError, PayrollConflictError) as error:
        raise _error(error) from error
    return Response(
        data,
        media_type=artifact.media_type,
        headers={
            "Content-Disposition": f'inline; filename="pay-statement-{statement_id}.html"',
            "ETag": f'"{artifact.digest}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.post(
    "/pay-statements/{statement_id}/artifact", response_model=dict[str, object]
)
async def render_pay_statement(
    statement_id: UUID, context: Manage, session: Session
) -> dict[str, object]:
    try:
        artifact = await _experience().render(
            session, context=context, statement_id=statement_id
        )
    except (PayrollAuthorizationError, PayrollConflictError) as error:
        raise _error(error) from error
    return {
        "artifact_id": artifact.id,
        "statement_id": artifact.statement_id,
        "media_type": artifact.media_type,
        "artifact_digest": artifact.digest,
        "lifecycle": artifact.lifecycle,
    }


@router.get("/pay-statements/{statement_id}/artifact")
async def administrative_pay_statement_artifact(
    statement_id: UUID, context: AdminRead, session: Session
) -> Response:
    try:
        artifact, data = await _experience().administrative_artifact(
            session, context=context, statement_id=statement_id
        )
    except (PayrollAuthorizationError, PayrollConflictError) as error:
        raise _error(error) from error
    return Response(
        data,
        media_type=artifact.media_type,
        headers={
            "Content-Disposition": f'inline; filename="pay-statement-{statement_id}.html"',
            "ETag": f'"{artifact.digest}"',
            "Cache-Control": "private, no-store",
        },
    )
