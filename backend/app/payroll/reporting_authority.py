"""Durable Payroll reporting, history-coverage, and filing-package authority."""

from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, AuditService, audit_service
from app.platform.permissions.authorization import AuthorizationContext

from .contracts import PayrollAuthorizationError, PayrollConflictError, canonical_digest
from .models import (
    PayrollFilingPackageRecord,
    PayrollHistoryCoverageRecord,
    PayrollReportingSnapshotRecord,
)
from .permissions import PayrollPermission
from .reporting import (
    FilingConfigurationAuthority,
    HistoryCoverageEvidence,
    PayrollReportingResult,
    ReportingState,
    _totals_document,
    prepare_filing_package,
)


class PayrollReportingAuthorityService:
    def __init__(self, *, audit: AuditService = audit_service) -> None:
        self._audit = audit

    async def create_coverage(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        start: date,
        end: date,
        source_authority: str,
        source_evidence: dict[str, object],
        complete: bool,
    ) -> PayrollHistoryCoverageRecord:
        self._require(context, PayrollPermission.REPORTING_MANAGE)
        evidence_digest = canonical_digest(source_evidence)
        identity = f"payroll-history-coverage:{canonical_digest({'company_id': str(context.company.id), 'start': start, 'end': end, 'source_authority': source_authority, 'evidence_digest': evidence_digest, 'complete': complete})}"
        existing = await session.scalar(
            select(PayrollHistoryCoverageRecord).where(
                PayrollHistoryCoverageRecord.company_id == context.company.id,
                PayrollHistoryCoverageRecord.coverage_identity == identity,
            )
        )
        if existing:
            return existing
        value = PayrollHistoryCoverageRecord(
            company_id=context.company.id,
            coverage_start=start,
            coverage_end=end,
            source_authority=source_authority,
            source_evidence=source_evidence,
            complete=complete,
            coverage_identity=identity,
            evidence_digest=evidence_digest,
            lifecycle="draft",
            created_by_user_id=context.user.id,
        )
        session.add(value)
        await session.commit()
        return value

    async def approve_coverage(
        self, session: AsyncSession, *, context: AuthorizationContext, coverage_id: UUID
    ) -> PayrollHistoryCoverageRecord:
        self._require(context, PayrollPermission.REPORTING_APPROVE)
        value = await session.scalar(
            select(PayrollHistoryCoverageRecord)
            .where(
                PayrollHistoryCoverageRecord.company_id == context.company.id,
                PayrollHistoryCoverageRecord.id == coverage_id,
            )
            .with_for_update()
        )
        if value is None:
            raise PayrollConflictError("history coverage was not found")
        if value.created_by_user_id == context.user.id:
            raise PayrollAuthorizationError(
                "history coverage requires independent approval"
            )
        if value.lifecycle == "approved":
            return value
        if value.lifecycle != "draft":
            raise PayrollConflictError("draft history coverage is required")
        value.lifecycle, value.approved_by_user_id, value.approved_at = (
            "approved",
            context.user.id,
            datetime.now(timezone.utc),
        )
        await session.commit()
        return value

    async def coverage_evidence(
        self, session: AsyncSession, *, company_id: UUID, coverage_id: UUID
    ) -> HistoryCoverageEvidence:
        value = await session.scalar(
            select(PayrollHistoryCoverageRecord).where(
                PayrollHistoryCoverageRecord.company_id == company_id,
                PayrollHistoryCoverageRecord.id == coverage_id,
            )
        )
        if value is None:
            raise PayrollConflictError("history coverage was not found")
        return HistoryCoverageEvidence(
            str(value.id),
            value.evidence_digest,
            value.company_id,
            value.coverage_start,
            value.coverage_end,
            value.lifecycle == "approved",
            value.complete,
            value.source_authority,
        )

    async def persist_report(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        result: PayrollReportingResult,
    ) -> PayrollReportingSnapshotRecord:
        self._require(context, PayrollPermission.REPORTING_MANAGE)
        if result.company_id != context.company.id:
            raise PayrollConflictError("cross-Company reporting result")
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": result.report_id},
        )
        existing = await session.scalar(
            select(PayrollReportingSnapshotRecord).where(
                PayrollReportingSnapshotRecord.company_id == context.company.id,
                PayrollReportingSnapshotRecord.report_identity == result.report_id,
            )
        )
        if existing:
            if existing.report_digest != result.report_digest:
                raise PayrollConflictError("contradictory report replay")
            return existing
        value = PayrollReportingSnapshotRecord(
            company_id=result.company_id,
            employee_id=result.employee_id,
            period_identity=result.period.identity,
            period_kind=result.period.kind.value,
            period_start=result.period.start,
            period_end=result.period.end,
            currency=result.currency,
            state=result.state.value,
            totals=_totals_document(result.totals),
            source_ids=list(result.source_ids),
            source_digests=list(result.source_digests),
            coverage_evidence_id=result.coverage_evidence_id,
            blockers=list(result.blockers),
            reconciliation_digest=result.reconciliation_digest,
            report_identity=result.report_id,
            report_digest=result.report_digest,
            definition_version=result.version,
            created_by_user_id=context.user.id,
        )
        session.add(value)
        await session.flush()
        self._stage(
            session,
            context,
            value.id,
            EventType.PAYROLL_REPORT_CREATED,
            "report_created",
            {
                "report_id": str(value.id),
                "report_digest": value.report_digest,
                "period_identity": value.period_identity,
                "state": value.state,
            },
        )
        await session.commit()
        return value

    async def prepare_filing(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        snapshot_id: UUID,
        authority: FilingConfigurationAuthority,
    ) -> PayrollFilingPackageRecord:
        self._require(context, PayrollPermission.REPORTING_APPROVE)
        snapshot = await session.scalar(
            select(PayrollReportingSnapshotRecord).where(
                PayrollReportingSnapshotRecord.company_id == context.company.id,
                PayrollReportingSnapshotRecord.id == snapshot_id,
            )
        )
        if snapshot is None or snapshot.state != ReportingState.AUTHORITATIVE.value:
            raise PayrollConflictError("authoritative reporting snapshot is required")
        from .reporting import (
            PayrollReportingResult,
            ReportingPeriod,
            ReportingPeriodKind,
            ReportingTotals,
        )

        totals = (
            ReportingTotals(
                **{
                    key: __import__("decimal").Decimal(str(value))
                    for key, value in (snapshot.totals or {}).items()
                }
            )
            if snapshot.totals
            else None
        )
        result = PayrollReportingResult(
            snapshot.report_identity,
            snapshot.report_digest,
            snapshot.company_id,
            snapshot.employee_id,
            ReportingPeriod(
                snapshot.period_identity,
                ReportingPeriodKind(snapshot.period_kind),
                snapshot.period_start,
                snapshot.period_end,
            ),
            snapshot.currency,
            ReportingState(snapshot.state),
            totals,
            tuple(snapshot.source_ids),
            tuple(snapshot.source_digests),
            snapshot.coverage_evidence_id,
            tuple(snapshot.blockers),
            snapshot.reconciliation_digest,
            snapshot.definition_version,
        )
        package = prepare_filing_package(result=result, authority=authority)
        existing = await session.scalar(
            select(PayrollFilingPackageRecord).where(
                PayrollFilingPackageRecord.company_id == context.company.id,
                PayrollFilingPackageRecord.package_identity == package.package_id,
            )
        )
        if existing:
            return existing
        value = PayrollFilingPackageRecord(
            company_id=context.company.id,
            reporting_snapshot_id=snapshot.id,
            reporting_digest=snapshot.report_digest,
            configuration_id=authority.authority_id,
            configuration_digest=authority.authority_digest,
            jurisdiction_reference=package.jurisdiction_reference,
            package_type=package.package_type,
            schema_version=package.schema_version,
            payload_digest=package.payload_digest,
            package_identity=package.package_id,
            package_digest=package.package_digest,
            state=package.state,
            created_by_user_id=context.user.id,
        )
        session.add(value)
        await session.flush()
        self._stage(
            session,
            context,
            value.id,
            EventType.PAYROLL_FILING_PACKAGE_PREPARED,
            "filing_package_prepared",
            {
                "package_id": str(value.id),
                "package_digest": value.package_digest,
                "state": value.state,
            },
        )
        await session.commit()
        return value

    @staticmethod
    def _require(context: AuthorizationContext, permission: str) -> None:
        if not context.has_permission(permission):
            raise PayrollAuthorizationError("Payroll reporting permission denied")

    def _stage(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        resource_id: UUID,
        event: EventType,
        action: str,
        details: dict[str, object],
    ) -> None:
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=event,
                entity_type="payroll_reporting",
                entity_id=resource_id,
                company_id=context.company.id,
                user_id=context.user.id,
                payload=details,
            ),
        )
        self._audit.stage(
            session,
            AuditEntry(
                action=f"payroll.reporting.{action}",
                resource_type="payroll_reporting",
                actor_user_id=context.user.id,
                company_id=context.company.id,
                resource_id=resource_id,
                details=details,
            ),
        )
