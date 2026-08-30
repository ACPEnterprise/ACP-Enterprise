"""Authenticated employee and Payroll-admin boundary."""

from datetime import date
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.dependencies import require_permission
from app.platform.reliability.correlation import current_correlation_id
from app.platform.reliability.failures import ClientRecovery, FailureCode, SafeFailure

from .compliance import (
    DraftComplianceSchema,
    PayrollComplianceService,
    ProtectedPayrollReportStorage,
)
from .contracts import PayrollAuthorizationError, PayrollConflictError
from .models import (
    PayrollComplianceSchemaRecord,
    PayrollFilingPackageRecord,
    PayrollReportingSnapshotRecord,
)
from .operations import PayrollOperationsService
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
ReportingManage = Annotated[AuthorizationContext, Depends(require_permission(PayrollPermission.REPORTING_MANAGE))]
ReportingApprove = Annotated[AuthorizationContext, Depends(require_permission(PayrollPermission.REPORTING_APPROVE))]


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


class ComplianceSchemaWrite(BaseModel):
    jurisdiction_reference: str
    package_family: str
    tax_year: int
    quarter: int | None = None
    schema_version: str
    rule_version: str
    required_evidence: list[str]
    legal_content_slots: list[str] = Field(default_factory=list)
    effective_start: date
    effective_end: date | None = None


class ComplianceSchemaMetadata(BaseModel):
    id: UUID
    jurisdiction_reference: str
    package_family: str
    tax_year: int
    quarter: int | None
    schema_version: str
    rule_version: str
    required_evidence: list[str]
    legal_content_slots: list[str]
    lifecycle: str
    schema_digest: str


class FilingPackagePrepare(BaseModel):
    report_id: UUID
    schema_id: UUID
    supersedes_package_id: UUID | None = None
    amendment_reason: str | None = Field(default=None, max_length=120)


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
        raise _storage_unavailable()
    return PayrollPayStatementExperienceService(ProtectedStatementStorage(Path(root)))


def _compliance() -> PayrollComplianceService:
    root = settings.payroll_paystatement_artifact_root
    if not root:
        raise _storage_unavailable()
    return PayrollComplianceService(ProtectedPayrollReportStorage(Path(root)))


def _schema_metadata(value: PayrollComplianceSchemaRecord) -> ComplianceSchemaMetadata:
    return ComplianceSchemaMetadata(id=value.id, jurisdiction_reference=value.jurisdiction_reference, package_family=value.package_family, tax_year=value.tax_year, quarter=value.quarter, schema_version=value.schema_version, rule_version=value.rule_version, required_evidence=value.required_evidence, legal_content_slots=value.legal_content_slots, lifecycle=value.lifecycle, schema_digest=value.schema_digest)


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
        failure = SafeFailure(
            FailureCode.FORBIDDEN,
            "Payroll access is denied.",
            ClientRecovery.TERMINAL_FAILURE,
            current_correlation_id(),
        )
        return HTTPException(status.HTTP_403_FORBIDDEN, failure.detail())
    if isinstance(error, PayrollConflictError):
        failure = SafeFailure(
            FailureCode.RESOURCE_STATE_CONFLICT,
            "Payroll operation conflicts with current authority.",
            ClientRecovery.RETRY_AFTER_REFRESH,
            current_correlation_id(),
        )
        return HTTPException(status.HTTP_409_CONFLICT, failure.detail())
    if isinstance(error, ValueError):
        failure = SafeFailure(
            FailureCode.VALIDATION,
            "Payroll request requires correction.",
            ClientRecovery.USER_CORRECTION_REQUIRED,
            current_correlation_id(),
        )
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, failure.detail())
    if isinstance(error, OSError):
        return _storage_unavailable()
    failure = SafeFailure(
        FailureCode.INTERNAL_FAILURE,
        "Payroll operation failed safely.",
        ClientRecovery.OWNER_ADMIN_ACTION_REQUIRED,
        current_correlation_id(),
    )
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, failure.detail())


def _storage_unavailable() -> HTTPException:
    failure = SafeFailure(
        FailureCode.DEPENDENCY_UNAVAILABLE,
        "Protected Payroll storage is unavailable.",
        ClientRecovery.OWNER_ADMIN_ACTION_REQUIRED,
        current_correlation_id(),
    )
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, failure.detail())


def _not_found() -> HTTPException:
    failure = SafeFailure(
        FailureCode.NOT_FOUND,
        "Payroll report was not found.",
        ClientRecovery.TERMINAL_FAILURE,
        current_correlation_id(),
    )
    return HTTPException(status.HTTP_404_NOT_FOUND, failure.detail())


@router.get("/reporting", response_model=list[PayrollReportingMetadata])
async def list_payroll_reporting(
    context: ReportingRead,
    session: Session,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[PayrollReportingMetadata]:
    values = (
        await session.scalars(
            select(PayrollReportingSnapshotRecord)
            .where(PayrollReportingSnapshotRecord.company_id == context.company.id)
            .order_by(
                PayrollReportingSnapshotRecord.period_end.desc(),
                PayrollReportingSnapshotRecord.created_at.desc(),
                PayrollReportingSnapshotRecord.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return [_report_metadata(value) for value in values]


@router.get("/operations/summary", response_model=dict[str, object])
async def payroll_operations_summary(context: ReportingRead, session: Session) -> dict[str, object]:
    value = await PayrollOperationsService().summary(session, context=context)
    return {"run_counts": value.run_counts, "member_dispositions": value.member_dispositions, "payment_counts": value.payment_counts, "remittance_counts": value.remittance_counts, "reporting_counts": value.reporting_counts, "statement_counts": value.statement_counts, "adjustment_counts": value.adjustment_counts, "history_ready": value.history_ready, "aggregate_approved_gross": str(value.aggregate_approved_gross), "aggregate_approved_net": str(value.aggregate_approved_net), "blocker_count": value.blocker_count, "reconciliation_state": value.reconciliation_state, "provider_readiness": {"filing": value.filing_provider_state, "payment": value.payment_provider_state, "remittance": value.remittance_provider_state}}


@router.get("/compliance/schemas", response_model=list[ComplianceSchemaMetadata])
async def compliance_schemas(
    context: ReportingRead,
    session: Session,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ComplianceSchemaMetadata]:
    values = (
        await session.scalars(
            select(PayrollComplianceSchemaRecord)
            .where(PayrollComplianceSchemaRecord.company_id == context.company.id)
            .order_by(
                PayrollComplianceSchemaRecord.tax_year.desc(),
                PayrollComplianceSchemaRecord.created_at.desc(),
                PayrollComplianceSchemaRecord.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return [_schema_metadata(value) for value in values]


@router.post("/compliance/schemas", response_model=ComplianceSchemaMetadata)
async def create_compliance_schema(body: ComplianceSchemaWrite, context: ReportingManage, session: Session) -> ComplianceSchemaMetadata:
    try:
        value = await _compliance().create_schema(session, context=context, draft=DraftComplianceSchema(body.jurisdiction_reference, body.package_family, body.tax_year, body.quarter, body.schema_version, body.rule_version, tuple(body.required_evidence), tuple(body.legal_content_slots), body.effective_start, body.effective_end))
    except (PayrollAuthorizationError, PayrollConflictError, ValueError) as error:
        raise _error(error) from error
    return _schema_metadata(value)


@router.post("/compliance/schemas/{schema_id}/approve", response_model=ComplianceSchemaMetadata)
async def approve_compliance_schema(schema_id: UUID, context: ReportingApprove, session: Session) -> ComplianceSchemaMetadata:
    try:
        return _schema_metadata(await _compliance().approve_schema(session, context=context, schema_id=schema_id))
    except (PayrollAuthorizationError, PayrollConflictError) as error:
        raise _error(error) from error


@router.post("/reporting/{report_id}/artifact", response_model=dict[str, object])
async def render_payroll_report(report_id: UUID, context: ReportingManage, session: Session) -> dict[str, object]:
    try:
        value = await _compliance().render_report(session, context=context, report_id=report_id)
    except (PayrollAuthorizationError, PayrollConflictError, OSError) as error:
        raise _error(error) from error
    return {"artifact_id": value.id, "source_type": value.source_type, "source_id": value.source_id, "artifact_digest": value.digest, "media_type": value.media_type, "lifecycle": value.lifecycle}


@router.post("/filing-packages/prepare", response_model=PayrollFilingPackageMetadata)
async def prepare_filing_package(body: FilingPackagePrepare, context: ReportingApprove, session: Session) -> PayrollFilingPackageMetadata:
    try:
        value = await _compliance().prepare_package(session, context=context, report_id=body.report_id, schema_id=body.schema_id, supersedes_package_id=body.supersedes_package_id, amendment_evidence=({"reason": body.amendment_reason} if body.supersedes_package_id and body.amendment_reason else None))
    except (PayrollAuthorizationError, PayrollConflictError, ValueError) as error:
        raise _error(error) from error
    return PayrollFilingPackageMetadata(id=value.id, reporting_snapshot_id=value.reporting_snapshot_id, jurisdiction_reference=value.jurisdiction_reference, package_type=value.package_type, schema_version=value.schema_version, state=value.state, package_digest=value.package_digest)


@router.post("/filing-packages/{package_id}/artifact", response_model=dict[str, object])
async def render_filing_package_preview(package_id: UUID, context: ReportingManage, session: Session) -> dict[str, object]:
    try:
        value = await _compliance().render_filing_preview(session, context=context, package_id=package_id)
    except (PayrollAuthorizationError, PayrollConflictError, OSError) as error:
        raise _error(error) from error
    return {"artifact_id": value.id, "source_type": value.source_type, "source_id": value.source_id, "artifact_digest": value.digest, "media_type": value.media_type, "lifecycle": value.lifecycle}


@router.get("/reporting-artifacts/{artifact_id}")
async def retrieve_payroll_report_artifact(artifact_id: UUID, context: ReportingRead, session: Session) -> Response:
    try:
        artifact, data = await _compliance().retrieve(session, context=context, artifact_id=artifact_id)
    except (PayrollAuthorizationError, PayrollConflictError, OSError) as error:
        raise _error(error) from error
    return Response(data, media_type=artifact.media_type, headers={"Content-Disposition": f'inline; filename="payroll-report-{artifact.id}.html"', "ETag": f'"{artifact.digest}"', "Cache-Control": "private, no-store"})


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
        raise _not_found()
    return _report_metadata(value)


@router.get(
    "/reporting/{report_id}/filing-packages",
    response_model=list[PayrollFilingPackageMetadata],
)
async def payroll_filing_packages(
    report_id: UUID,
    context: ReportingRead,
    session: Session,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[PayrollFilingPackageMetadata]:
    report = await session.scalar(
        select(PayrollReportingSnapshotRecord.id).where(
            PayrollReportingSnapshotRecord.id == report_id,
            PayrollReportingSnapshotRecord.company_id == context.company.id,
        )
    )
    if report is None:
        raise _not_found()
    values = (
        await session.scalars(
            select(PayrollFilingPackageRecord)
            .where(
                PayrollFilingPackageRecord.reporting_snapshot_id == report_id,
                PayrollFilingPackageRecord.company_id == context.company.id,
            )
            .order_by(
                PayrollFilingPackageRecord.created_at.desc(),
                PayrollFilingPackageRecord.id.desc(),
            )
            .offset(offset)
            .limit(limit)
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
    context: OwnRead,
    session: Session,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[StatementMetadata]:
    try:
        return [
            _metadata(value)
            for value in await PayrollPayStatementService().list_own(
                session, context=context, limit=limit, offset=offset
            )
        ]
    except (PayrollAuthorizationError, PayrollConflictError) as error:
        raise _error(error) from error


@router.get("/me/payroll-status", response_model=dict[str, object])
async def own_payroll_status(context: OwnRead, session: Session) -> dict[str, object]:
    try:
        statement_count, current = await PayrollPayStatementService().own_summary(
            session, context=context
        )
    except (PayrollAuthorizationError, PayrollConflictError) as error:
        raise _error(error) from error
    return {"statement_count": statement_count, "current_statement_id": current.id if current else None, "current_pay_period_id": current.pay_period_id if current else None, "payment_status": current.payment_status if current else "unavailable", "ytd_status": current.ytd_status if current else "unavailable", "has_correction": bool(current and current.version > 1)}


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
    except (PayrollAuthorizationError, PayrollConflictError, OSError) as error:
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
    except (PayrollAuthorizationError, PayrollConflictError, OSError) as error:
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
    except (PayrollAuthorizationError, PayrollConflictError, OSError) as error:
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
