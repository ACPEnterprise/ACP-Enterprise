"""Safe Company-scoped Payroll operations and observability projection."""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.permissions.authorization import AuthorizationContext

from .contracts import PayrollAuthorizationError
from .models import (
    PayrollAdjustmentAuthorityRecord,
    PayrollFilingPackageRecord,
    PayrollHistoryCoverageRecord,
    PayrollPaymentExecutionRecord,
    PayrollPaymentReleaseRecord,
    PayrollPayStatementArtifactRecord,
    PayrollPayStatementRecord,
    PayrollRemittanceInstructionRecord,
    PayrollRemittanceObligationRecord,
    PayrollReportingSnapshotRecord,
    PayrollRunMemberRecord,
    PayrollRunRecord,
)
from .permissions import PayrollPermission


@dataclass(frozen=True, slots=True)
class PayrollOperationsSummary:
    run_counts: dict[str, int]
    member_dispositions: dict[str, int]
    payment_counts: dict[str, int]
    remittance_counts: dict[str, int]
    reporting_counts: dict[str, int]
    statement_counts: dict[str, int]
    adjustment_counts: dict[str, int]
    history_ready: bool
    aggregate_approved_gross: Decimal
    aggregate_approved_net: Decimal
    blocker_count: int
    reconciliation_state: str
    filing_provider_state: str = "provider_not_configured"
    payment_provider_state: str = "provider_not_configured"
    remittance_provider_state: str = "provider_not_configured"


class PayrollOperationsService:
    async def summary(
        self, session: AsyncSession, *, context: AuthorizationContext
    ) -> PayrollOperationsSummary:
        if not context.has_permission(PayrollPermission.RUN_READ):
            raise PayrollAuthorizationError("Payroll run read permission denied")
        company_id = context.company.id
        run_counts = await self._states(
            session, PayrollRunRecord, PayrollRunRecord.lifecycle, company_id
        )
        member_dispositions = await self._states(
            session,
            PayrollRunMemberRecord,
            PayrollRunMemberRecord.disposition,
            company_id,
        )
        releases = await self._states(
            session,
            PayrollPaymentReleaseRecord,
            PayrollPaymentReleaseRecord.lifecycle,
            company_id,
        )
        executions = await self._states(
            session,
            PayrollPaymentExecutionRecord,
            PayrollPaymentExecutionRecord.lifecycle,
            company_id,
        )
        payment_counts = {
            **{f"release:{key}": value for key, value in releases.items()},
            **{f"execution:{key}": value for key, value in executions.items()},
        }
        obligations = await self._states(
            session,
            PayrollRemittanceObligationRecord,
            PayrollRemittanceObligationRecord.lifecycle,
            company_id,
        )
        instructions = await self._states(
            session,
            PayrollRemittanceInstructionRecord,
            PayrollRemittanceInstructionRecord.lifecycle,
            company_id,
        )
        remittance_counts = {
            **{f"obligation:{key}": value for key, value in obligations.items()},
            **{f"instruction:{key}": value for key, value in instructions.items()},
        }
        reporting_counts = await self._states(
            session,
            PayrollReportingSnapshotRecord,
            PayrollReportingSnapshotRecord.state,
            company_id,
        )
        filing_counts = await self._states(
            session,
            PayrollFilingPackageRecord,
            PayrollFilingPackageRecord.state,
            company_id,
        )
        reporting_counts.update(
            {f"filing:{key}": value for key, value in filing_counts.items()}
        )
        statements = await self._states(
            session,
            PayrollPayStatementRecord,
            PayrollPayStatementRecord.lifecycle,
            company_id,
        )
        artifact_count = int(
            await session.scalar(
                select(func.count(PayrollPayStatementArtifactRecord.id)).where(
                    PayrollPayStatementArtifactRecord.company_id == company_id
                )
            )
            or 0
        )
        statements["artifacts_ready"] = artifact_count
        adjustments = await self._states(
            session,
            PayrollAdjustmentAuthorityRecord,
            PayrollAdjustmentAuthorityRecord.lifecycle,
            company_id,
        )
        history_ready = bool(
            await session.scalar(
                select(PayrollHistoryCoverageRecord.id).where(
                    PayrollHistoryCoverageRecord.company_id == company_id,
                    PayrollHistoryCoverageRecord.lifecycle == "approved",
                    PayrollHistoryCoverageRecord.complete.is_(True),
                )
            )
        )
        aggregate = (
            await session.execute(
                select(
                    func.coalesce(func.sum(PayrollRunRecord.aggregate_gross), 0),
                    func.coalesce(func.sum(PayrollRunRecord.aggregate_net_pay), 0),
                ).where(
                    PayrollRunRecord.company_id == company_id,
                    PayrollRunRecord.lifecycle == "approved",
                )
            )
        ).one()
        blocker_count = member_dispositions.get("blocked", 0)
        incomplete_reports = sum(
            reporting_counts.get(state, 0)
            for state in ("partial", "unavailable", "conflicting")
        )
        reconciliation_state = (
            "attention_required"
            if blocker_count or incomplete_reports
            else "reconciled_or_no_activity"
        )
        return PayrollOperationsSummary(
            run_counts,
            member_dispositions,
            payment_counts,
            remittance_counts,
            reporting_counts,
            statements,
            adjustments,
            history_ready,
            Decimal(aggregate[0]),
            Decimal(aggregate[1]),
            blocker_count,
            reconciliation_state,
        )

    @staticmethod
    async def _states(session, model, state_column, company_id) -> dict[str, int]:
        values = (
            await session.execute(
                select(state_column, func.count(model.id))
                .where(model.company_id == company_id)
                .group_by(state_column)
            )
        ).all()
        return {str(state): int(count) for state, count in values}
