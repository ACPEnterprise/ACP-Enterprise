"""Safe Company-scoped Payroll operations and observability projection."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.platform.employees.models import Employee
from app.platform.permissions.authorization import AuthorizationContext
from app.timekeeping.models import (
    PayPeriod,
    PayrollTimeInputRecord,
    WorkdayTimeEntryRevision,
)
from app.timekeeping.permissions import TimekeepingPermission

from .contracts import PayrollAuthorizationError
from .models import (
    CompanyPayrollPolicyVersion,
    EmployeeCompensationAuthorityVersion,
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


@dataclass(frozen=True, slots=True)
class PayrollPeriodEmployee:
    employee_id: UUID
    employee_number: str
    display_name: str
    home_branch_id: UUID | None
    accepted_minutes: int
    regular_candidate_minutes: int | None
    overtime_candidate_minutes: int | None
    compensation_readiness: str
    withholding_readiness: str
    gross_pay_readiness: str
    exception_codes: tuple[str, ...]
    payroll_review_status: str
    time_evidence_revision_ids: tuple[UUID, ...]
    time_snapshot_state: str
    gross_calculation_state: str


@dataclass(frozen=True, slots=True)
class PayrollPeriodOperations:
    contract_version: str
    pay_period_id: UUID
    period_start: date
    period_end: date
    policy_readiness: str
    employees: tuple[PayrollPeriodEmployee, ...]
    limitations: tuple[str, ...]


class PayrollOperationsService:
    async def period(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        pay_period_id: UUID,
    ) -> PayrollPeriodOperations:
        if not context.has_permission(
            PayrollPermission.REPORTING_READ
        ) or not context.has_permission(TimekeepingPermission.ADMIN_READ):
            raise PayrollAuthorizationError(
                "Payroll period operations require Payroll and Timekeeping read authority"
            )
        company_id = context.company.id
        period = await session.scalar(
            select(PayPeriod).where(
                PayPeriod.company_id == company_id, PayPeriod.id == pay_period_id
            )
        )
        if period is None:
            raise ValueError("pay period does not exist in this Company")
        branch_ids = (
            frozenset({context.active_branch.id})
            if context.active_branch is not None
            else context.authorized_branch_ids
        )
        employee_scope: ColumnElement[bool] = Employee.home_branch_id.in_(branch_ids)
        if context.active_branch is None:
            employee_scope = employee_scope | Employee.home_branch_id.is_(None)
        employees = tuple(
            (
                await session.scalars(
                    select(Employee)
                    .where(
                        Employee.company_id == company_id,
                        Employee.status == "active",
                        employee_scope,
                    )
                    .order_by(Employee.display_name, Employee.id)
                )
            ).all()
        )
        employee_ids = tuple(item.id for item in employees)
        revisions = await self._current_revisions(
            session, company_id, employee_ids, period.period_start, period.period_end
        )
        compensation_candidates = await self._rows_by_employee(
            session,
            select(EmployeeCompensationAuthorityVersion).where(
                EmployeeCompensationAuthorityVersion.company_id == company_id,
                EmployeeCompensationAuthorityVersion.employee_id.in_(employee_ids),
                EmployeeCompensationAuthorityVersion.lifecycle.in_(
                    ("approved", "superseded")
                ),
                EmployeeCompensationAuthorityVersion.effective_start
                <= period.period_start,
                or_(
                    EmployeeCompensationAuthorityVersion.effective_end.is_(None),
                    EmployeeCompensationAuthorityVersion.effective_end
                    > period.period_end,
                ),
            ),
        )
        compensations = {
            employee_id: self._remove_superseded(values, "supersedes_authority_id")
            for employee_id, values in compensation_candidates.items()
        }
        gross = await self._latest_by_employee(
            session,
            PayrollGrossCalculationResultRecord,
            company_id,
            pay_period_id,
            ("calculated", "under_review", "approved"),
        )
        tax = await self._latest_by_employee(
            session,
            PayrollTaxDeductionResultRecord,
            company_id,
            pay_period_id,
            ("calculated", "under_review", "approved"),
        )
        time_snapshots = await self._latest_time_snapshots(
            session, company_id, pay_period_id, employee_ids
        )
        run = await session.scalar(
            select(PayrollRunRecord)
            .where(
                PayrollRunRecord.company_id == company_id,
                PayrollRunRecord.pay_period_id == pay_period_id,
                PayrollRunRecord.lifecycle.in_(
                    ("assembled", "under_review", "reviewed", "approved")
                ),
            )
            .order_by(PayrollRunRecord.created_at.desc())
        )
        members: dict[UUID, PayrollRunMemberRecord] = {}
        if run is not None:
            members = {
                item.employee_id: item
                for item in (
                    await session.scalars(
                        select(PayrollRunMemberRecord).where(
                            PayrollRunMemberRecord.company_id == company_id,
                            PayrollRunMemberRecord.run_id == run.id,
                            PayrollRunMemberRecord.employee_id.in_(employee_ids),
                        )
                    )
                ).all()
            }
        policy_candidates = tuple(
            (
                await session.scalars(
                    select(CompanyPayrollPolicyVersion).where(
                        CompanyPayrollPolicyVersion.company_id == company_id,
                        CompanyPayrollPolicyVersion.lifecycle.in_(
                            ("approved", "superseded")
                        ),
                        CompanyPayrollPolicyVersion.effective_start
                        <= period.period_start,
                        or_(
                            CompanyPayrollPolicyVersion.effective_end.is_(None),
                            CompanyPayrollPolicyVersion.effective_end
                            > period.period_end,
                        ),
                    )
                )
            ).all()
        )
        policy_count = len(
            self._remove_superseded(policy_candidates, "supersedes_policy_id")
        )
        policy_readiness = (
            "READY"
            if policy_count == 1
            else "CONFLICTING"
            if policy_count
            else "MISSING_CONFIGURATION"
        )
        rows: list[PayrollPeriodEmployee] = []
        for employee in employees:
            current = tuple(
                item
                for item in revisions.get(employee.id, ())
                if item.branch_id in branch_ids
                or (context.active_branch is None and item.branch_id is None)
            )
            accepted = self._accepted_time_revisions(current)
            accepted_minutes = sum(self._revision_minutes(item) for item in accepted)
            comp_count = len(compensations.get(employee.id, ()))
            comp_state = (
                "READY"
                if comp_count == 1
                else "CONFLICTING"
                if comp_count
                else "MISSING_CONFIGURATION"
            )
            gross_value = gross.get(employee.id)
            tax_value = tax.get(employee.id)
            snapshot = time_snapshots.get(employee.id)
            accepted_ids = tuple(item.id for item in accepted)
            snapshot_ids = (
                frozenset(UUID(item) for item in snapshot.approved_revision_ids)
                if snapshot is not None
                else frozenset()
            )
            time_snapshot_state = (
                "MISSING"
                if snapshot is None
                else "CURRENT"
                if snapshot_ids == frozenset(accepted_ids)
                else "STALE_TIME_EVIDENCE"
            )
            gross_calculation_state = (
                "NOT_CALCULATED"
                if gross_value is None
                else "CURRENT"
                if snapshot is not None
                and time_snapshot_state == "CURRENT"
                and gross_value.time_snapshot_id == snapshot.snapshot_identity
                and gross_value.time_snapshot_digest == snapshot.snapshot_digest
                else "STALE_TIME_EVIDENCE"
            )
            regular, overtime = self._earning_minutes(gross_value)
            exceptions: set[str] = set()
            if not current:
                exceptions.add("TIME_EVIDENCE_MISSING")
            elif len(accepted) != len(current):
                exceptions.add("TIME_REVIEW_INCOMPLETE")
            if comp_state != "READY":
                exceptions.add("COMPENSATION_" + comp_state)
            if policy_readiness != "READY":
                exceptions.add("PAYROLL_POLICY_" + policy_readiness)
            if gross_value is None:
                exceptions.add("GROSS_PAY_NOT_CALCULATED")
            elif gross_calculation_state != "CURRENT":
                exceptions.add("GROSS_PAY_STALE_TIME_EVIDENCE")
            if time_snapshot_state == "STALE_TIME_EVIDENCE":
                exceptions.add("PAYROLL_TIME_SNAPSHOT_STALE")
            if tax_value is None:
                exceptions.add("WITHHOLDING_NOT_CALCULATED")
            member = members.get(employee.id)
            review = (
                member.disposition.upper()
                if member is not None
                else gross_value.review_state.upper()
                if gross_value is not None
                else "NOT_STARTED"
            )
            rows.append(
                PayrollPeriodEmployee(
                    employee.id,
                    employee.employee_number,
                    employee.display_name,
                    employee.home_branch_id,
                    accepted_minutes,
                    regular,
                    overtime,
                    comp_state,
                    tax_value.lifecycle.upper()
                    if tax_value is not None
                    else "MISSING_CONFIGURATION_OR_CALCULATION",
                    gross_value.lifecycle.upper()
                    if gross_value is not None
                    else "NOT_CALCULATED",
                    tuple(sorted(exceptions)),
                    review,
                    accepted_ids,
                    time_snapshot_state,
                    gross_calculation_state,
                )
            )
        return PayrollPeriodOperations(
            "PAYROLL.PERIOD.OFFICE.UX.v1",
            period.id,
            period.period_start,
            period.period_end,
            policy_readiness,
            tuple(rows),
            (
                "Regular and overtime minutes appear only from persisted Payroll calculation evidence.",
                "Missing compensation, withholding, policy, or time authority remains visible and is never inferred.",
                "This projection cannot transmit Payroll, move money, or post Accounting.",
            ),
        )

    @staticmethod
    async def _latest_time_snapshots(
        session: AsyncSession,
        company_id: UUID,
        pay_period_id: UUID,
        employee_ids: tuple[UUID, ...],
    ) -> dict[UUID, PayrollTimeInputRecord]:
        if not employee_ids:
            return {}
        values = tuple(
            (
                await session.scalars(
                    select(PayrollTimeInputRecord)
                    .where(
                        PayrollTimeInputRecord.company_id == company_id,
                        PayrollTimeInputRecord.pay_period_id == pay_period_id,
                        PayrollTimeInputRecord.employee_id.in_(employee_ids),
                    )
                    .order_by(
                        PayrollTimeInputRecord.created_at.desc(),
                        PayrollTimeInputRecord.id.desc(),
                    )
                )
            ).all()
        )
        result: dict[UUID, PayrollTimeInputRecord] = {}
        for value in values:
            result.setdefault(value.employee_id, value)
        return result

    @staticmethod
    def _accepted_time_revisions(
        revisions: tuple[WorkdayTimeEntryRevision, ...],
    ) -> tuple[WorkdayTimeEntryRevision, ...]:
        """Only the authoritative current approved state is payable evidence.

        An approval timestamp on a corrected successor is lineage, not permission
        to reuse superseded paid time.
        """

        return tuple(item for item in revisions if item.state == "approved")

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
                            PayrollGrossCalculationResultRecord.company_id
                            == context.company.id,
                            PayrollGrossCalculationResultRecord.id
                            == member.gross_result_id,
                        )
                    )
                    if member.gross_result_id
                    else None
                )
                tax = (
                    await session.scalar(
                        select(PayrollTaxDeductionResultRecord).where(
                            PayrollTaxDeductionResultRecord.company_id
                            == context.company.id,
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
                            PayrollTimeInputRecord.snapshot_identity
                            == gross.time_snapshot_id,
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
                        "employee_number": employee.employee_number
                        if employee
                        else "unavailable",
                        "employee_name": employee.display_name
                        if employee
                        else "Employee unavailable",
                        "status": "BLOCKED_FOR_PAYROLL"
                        if member.disposition == "blocked"
                        else member.disposition.upper(),
                        "blockers": member.blocker_codes,
                        "accepted_minutes": time.total_approved_minutes
                        if time
                        else None,
                        "regular_minutes": regular_minutes if gross else None,
                        "overtime_minutes": overtime_minutes if gross else None,
                        "compensation_authority_id": str(
                            gross.compensation_authority_id
                        )
                        if gross
                        else None,
                        "compensation_authority_digest": gross.compensation_digest
                        if gross
                        else None,
                        "earnings": earning,
                        "withholdings_deductions_liabilities": tax.components
                        if tax
                        else [],
                        "gross": str(tax.gross_pay) if tax else None,
                        "employee_taxes": str(tax.employee_tax_total) if tax else None,
                        "deductions": str(tax.employee_deduction_total)
                        if tax
                        else None,
                        "net_pay": str(tax.net_pay_candidate) if tax else None,
                        "employer_liabilities": str(tax.employer_contribution_total)
                        if tax
                        else None,
                        "tax_rule_version": tax.calculation_version if tax else None,
                        "money_version": tax.money_version if tax else None,
                        "calculation_digest": tax.calculation_digest if tax else None,
                        "job_labor_allocation": "UNAVAILABLE_NO_AUTHORITATIVE_JOB_ALLOCATION"
                        if gross
                        else None,
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
                        "employer_liabilities": str(
                            run.aggregate_employer_contributions
                        ),
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

    @staticmethod
    async def _current_revisions(session, company_id, employee_ids, start, end):
        if not employee_ids:
            return {}
        values = tuple(
            (
                await session.scalars(
                    select(WorkdayTimeEntryRevision)
                    .where(
                        WorkdayTimeEntryRevision.company_id == company_id,
                        WorkdayTimeEntryRevision.employee_id.in_(employee_ids),
                        WorkdayTimeEntryRevision.work_date >= start,
                        WorkdayTimeEntryRevision.work_date <= end,
                    )
                    .order_by(
                        WorkdayTimeEntryRevision.entry_id,
                        WorkdayTimeEntryRevision.revision_number.desc(),
                    )
                )
            ).all()
        )
        current = {}
        for item in values:
            current.setdefault(item.entry_id, item)
        grouped = {}
        for item in current.values():
            grouped.setdefault(item.employee_id, []).append(item)
        return {key: tuple(value) for key, value in grouped.items()}

    @staticmethod
    async def _rows_by_employee(session, query):
        values = (await session.scalars(query)).all()
        grouped = {}
        for item in values:
            grouped.setdefault(item.employee_id, []).append(item)
        return {key: tuple(value) for key, value in grouped.items()}

    @staticmethod
    async def _latest_by_employee(
        session, model, company_id, pay_period_id, lifecycles
    ):
        values = (
            await session.scalars(
                select(model)
                .where(
                    model.company_id == company_id,
                    model.pay_period_id == pay_period_id,
                    model.lifecycle.in_(lifecycles),
                )
                .order_by(model.created_at.desc(), model.id.desc())
            )
        ).all()
        return {item.employee_id: item for item in reversed(values)}

    @staticmethod
    def _revision_minutes(value) -> int:
        if value.approved_duration_minutes is not None:
            return value.approved_duration_minutes
        if value.start_at is not None and value.end_at is not None:
            return int((value.end_at - value.start_at).total_seconds() // 60)
        return 0

    @staticmethod
    def _earning_minutes(value) -> tuple[int | None, int | None]:
        if value is None:
            return None, None
        regular = 0
        overtime = 0
        found_regular = False
        found_overtime = False
        for component in value.earning_components:
            minutes = component.get("payable_minutes")
            if not isinstance(minutes, int):
                continue
            if component.get("component_type") == "regular":
                regular += minutes
                found_regular = True
            elif component.get("component_type") == "overtime_premium":
                overtime += minutes
                found_overtime = True
        return regular if found_regular else None, overtime if found_overtime else 0

    @staticmethod
    def _remove_superseded(values, predecessor_field):
        predecessor_ids = {
            getattr(item, predecessor_field)
            for item in values
            if getattr(item, predecessor_field) is not None
        }
        return tuple(item for item in values if item.id not in predecessor_ids)
