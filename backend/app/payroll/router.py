"""Authenticated employee and Payroll-admin pay-statement boundary."""

from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.dependencies import require_permission

from .contracts import PayrollAuthorizationError, PayrollConflictError
from .models import PayrollFilingPackageRecord, PayrollReportingSnapshotRecord
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
ReportingRead = Annotated[
    AuthorizationContext,
    Depends(require_permission(PayrollPermission.REPORTING_READ)),
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


class PayrollReportingMetadata(BaseModel):
    id: UUID
    employee_id: UUID | None
    period_identity: str
    period_kind: str
    period_start: str
    period_end: str
    currency: str | None
    state: str
    totals: dict[str, object] | None
    blockers: list[str]
    report_digest: str


class PayrollFilingPackageMetadata(BaseModel):
    id: UUID
    reporting_snapshot_id: UUID
    jurisdiction_reference: str
    package_type: str
    schema_version: str
    state: str
    package_digest: str


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


def _report_metadata(value: PayrollReportingSnapshotRecord) -> PayrollReportingMetadata:
    return PayrollReportingMetadata(
        id=value.id,
        employee_id=value.employee_id,
        period_identity=value.period_identity,
        period_kind=value.period_kind,
        period_start=value.period_start.isoformat(),
        period_end=value.period_end.isoformat(),
        currency=value.currency,
        state=value.state,
        totals=value.totals,
        blockers=value.blockers,
        report_digest=value.report_digest,
    )


def _error(error: Exception) -> HTTPException:
    if isinstance(error, PayrollAuthorizationError):
        return HTTPException(status.HTTP_403_FORBIDDEN, "Pay statement access denied.")
    return HTTPException(status.HTTP_409_CONFLICT, str(error))


@router.get("/reporting", response_model=list[PayrollReportingMetadata])
async def list_payroll_reporting(
    context: ReportingRead, session: Session
) -> list[PayrollReportingMetadata]:
    values = (
        await session.scalars(
            select(PayrollReportingSnapshotRecord)
            .where(PayrollReportingSnapshotRecord.company_id == context.company.id)
            .order_by(
                PayrollReportingSnapshotRecord.period_end.desc(),
                PayrollReportingSnapshotRecord.created_at.desc(),
            )
        )
    ).all()
    return [_report_metadata(value) for value in values]


@router.get(
    "/reporting/{report_id}", response_model=PayrollReportingMetadata
)
async def payroll_reporting_detail(
    report_id: UUID, context: ReportingRead, session: Session
) -> PayrollReportingMetadata:
    value = await session.scalar(
        select(PayrollReportingSnapshotRecord).where(
            PayrollReportingSnapshotRecord.id == report_id,
            PayrollReportingSnapshotRecord.company_id == context.company.id,
        )
    )
    if value is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payroll report not found.")
    return _report_metadata(value)


@router.get(
    "/reporting/{report_id}/filing-packages",
    response_model=list[PayrollFilingPackageMetadata],
)
async def payroll_filing_packages(
    report_id: UUID, context: ReportingRead, session: Session
) -> list[PayrollFilingPackageMetadata]:
    report = await session.scalar(
        select(PayrollReportingSnapshotRecord.id).where(
            PayrollReportingSnapshotRecord.id == report_id,
            PayrollReportingSnapshotRecord.company_id == context.company.id,
        )
    )
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payroll report not found.")
    values = (
        await session.scalars(
            select(PayrollFilingPackageRecord)
            .where(
                PayrollFilingPackageRecord.reporting_snapshot_id == report_id,
                PayrollFilingPackageRecord.company_id == context.company.id,
            )
            .order_by(PayrollFilingPackageRecord.created_at.desc())
        )
    ).all()
    return [
        PayrollFilingPackageMetadata(
            id=value.id,
            reporting_snapshot_id=value.reporting_snapshot_id,
            jurisdiction_reference=value.jurisdiction_reference,
            package_type=value.package_type,
            schema_version=value.schema_version,
            state=value.state,
            package_digest=value.package_digest,
        )
        for value in values
    ]


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
