"""Safe Company-scoped Payroll operations and observability projection."""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.employees.models import Employee
from app.platform.permissions.authorization import AuthorizationContext
from app.timekeeping.models import PayPeriod, PayrollTimeInputRecord

from .contracts import PayrollAuthorizationError
from .models import (
    PayrollAdjustmentAuthorityRecord,
    PayrollFilingPackageRecord,
    PayrollGrossCalculationResultRecord,
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
    PayrollTaxDeductionResultRecord,
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
    async def registers(
        self, session: AsyncSession, *, context: AuthorizationContext
    ) -> tuple[dict[str, object], ...]:
        """Project existing immutable run evidence into an owner operating register."""
        if not context.has_permission(PayrollPermission.REPORTING_READ):
            raise PayrollAuthorizationError("Payroll reporting permission denied")
        runs = tuple(
            (
                await session.scalars(
                    select(PayrollRunRecord)
                    .where(PayrollRunRecord.company_id == context.company.id)
                    .order_by(PayrollRunRecord.assembled_at.desc(), PayrollRunRecord.id)
                    .limit(50)
                )
            ).all()
        )
        result: list[dict[str, object]] = []
        for run in runs:
            period = await session.scalar(
                select(PayPeriod).where(
                    PayPeriod.company_id == context.company.id,
                    PayPeriod.id == run.pay_period_id,
                )
            )
            if period is None:
                continue
            members = tuple(
                (
                    await session.scalars(
                        select(PayrollRunMemberRecord)
                        .where(
                            PayrollRunMemberRecord.company_id == context.company.id,
                            PayrollRunMemberRecord.run_id == run.id,
                        )
                        .order_by(PayrollRunMemberRecord.employee_id)
                    )
                ).all()
            )
            rows: list[dict[str, object]] = []
            for member in members:
                employee = await session.scalar(
                    select(Employee).where(
                        Employee.company_id == context.company.id,
                        Employee.id == member.employee_id,
                    )
                )
                gross = (
                    await session.scalar(
                        select(PayrollGrossCalculationResultRecord).where(
                            PayrollGrossCalculationResultRecord.company_id == context.company.id,
                            PayrollGrossCalculationResultRecord.id == member.gross_result_id,
                        )
                    )
                    if member.gross_result_id
                    else None
                )
                tax = (
                    await session.scalar(
                        select(PayrollTaxDeductionResultRecord).where(
                            PayrollTaxDeductionResultRecord.company_id == context.company.id,
                            PayrollTaxDeductionResultRecord.id == member.tax_result_id,
                        )
                    )
                    if member.tax_result_id
                    else None
                )
                time = (
                    await session.scalar(
                        select(PayrollTimeInputRecord).where(
                            PayrollTimeInputRecord.company_id == context.company.id,
                            PayrollTimeInputRecord.employee_id == member.employee_id,
                            PayrollTimeInputRecord.pay_period_id == run.pay_period_id,
                            PayrollTimeInputRecord.snapshot_identity == gross.time_snapshot_id,
                        )
                    )
                    if gross and gross.time_snapshot_id
                    else None
                )
                earning = gross.earning_components if gross else []
                regular_minutes = sum(
                    int(item.get("payable_minutes", 0))
                    for item in earning
                    if item.get("kind") == "regular"
                )
                overtime_minutes = sum(
                    int(item.get("payable_minutes", 0))
                    for item in earning
                    if item.get("kind") == "overtime_premium"
                )
                rows.append(
                    {
                        "employee_id": str(member.employee_id),
                        "employee_number": employee.employee_number if employee else "unavailable",
                        "employee_name": employee.display_name if employee else "Employee unavailable",
                        "status": "BLOCKED_FOR_PAYROLL" if member.disposition == "blocked" else member.disposition.upper(),
                        "blockers": member.blocker_codes,
                        "accepted_minutes": time.total_approved_minutes if time else None,
                        "regular_minutes": regular_minutes if gross else None,
                        "overtime_minutes": overtime_minutes if gross else None,
                        "compensation_authority_id": str(gross.compensation_authority_id) if gross else None,
                        "compensation_authority_digest": gross.compensation_digest if gross else None,
                        "earnings": earning,
                        "withholdings_deductions_liabilities": tax.components if tax else [],
                        "gross": str(tax.gross_pay) if tax else None,
                        "employee_taxes": str(tax.employee_tax_total) if tax else None,
                        "deductions": str(tax.employee_deduction_total) if tax else None,
                        "net_pay": str(tax.net_pay_candidate) if tax else None,
                        "employer_liabilities": str(tax.employer_contribution_total) if tax else None,
                        "tax_rule_version": tax.calculation_version if tax else None,
                        "money_version": tax.money_version if tax else None,
                        "calculation_digest": tax.calculation_digest if tax else None,
                        "job_labor_allocation": "UNAVAILABLE_NO_AUTHORITATIVE_JOB_ALLOCATION" if gross else None,
                    }
                )
            result.append(
                {
                    "run_id": str(run.id),
                    "period_start": period.period_start.isoformat(),
                    "period_end": period.period_end.isoformat(),
                    "processing_date": period.processing_date.isoformat(),
                    "payday": period.payday.isoformat(),
                    "lifecycle": run.lifecycle,
                    "review_state": run.review_state,
                    "currency": run.currency,
                    "members": rows,
                    "liability_totals": {
                        "employee_taxes": str(run.aggregate_employee_taxes),
                        "employee_deductions": str(run.aggregate_employee_deductions),
                        "employer_liabilities": str(run.aggregate_employer_contributions),
                        "net_pay": str(run.aggregate_net_pay),
                    },
                    "manual_tax_filing_payment_required": True,
                    "run_digest": run.run_digest,
                }
            )
        return tuple(result)

    async def summary(
        self, session: AsyncSession, *, context: AuthorizationContext
    ) -> PayrollOperationsSummary:
        if not context.has_permission(PayrollPermission.REPORTING_READ):
            raise PayrollAuthorizationError("Payroll reporting permission denied")
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
