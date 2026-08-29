"""Protected immutable employee pay-statement authority."""

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, AuditService, audit_service
from app.platform.employees.models import Employee
from app.platform.permissions.authorization import AuthorizationContext

from .contracts import PayrollAuthorizationError, PayrollConflictError, canonical_digest
from .models import (
    PayrollAdjustmentResultRecord,
    PayrollGrossCalculationResultRecord,
    PayrollPaymentExecutionItemRecord,
    PayrollPaymentExecutionRecord,
    PayrollPaymentInstructionRecord,
    PayrollPaymentReleaseRecord,
    PayrollPayStatementRecord,
    PayrollReportingSnapshotRecord,
    PayrollRunMemberRecord,
    PayrollRunRecord,
    PayrollTaxDeductionResultRecord,
)
from .permissions import PayrollPermission

PAYSTATEMENT_VERSION = "payroll.pay-statement.v1"


@dataclass(frozen=True)
class PayStatementView:
    id: UUID
    employee_id: UUID
    pay_period_id: UUID
    version: int
    currency: str
    payment_status: str
    ytd_status: str
    lifecycle: str
    content: dict[str, object]
    digest: str


class PayrollPayStatementService:
    def __init__(self, *, audit: AuditService = audit_service) -> None:
        self._audit = audit

    async def create(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        run_id: UUID,
        employee_id: UUID,
        supersedes_statement_id: UUID | None = None,
        adjustment_result_id: UUID | None = None,
        reporting_snapshot_id: UUID | None = None,
    ) -> PayrollPayStatementRecord:
        self._require(context, PayrollPermission.STATEMENT_MANAGE)
        run = await session.scalar(
            select(PayrollRunRecord).where(
                PayrollRunRecord.company_id == context.company.id,
                PayrollRunRecord.id == run_id,
                PayrollRunRecord.lifecycle == "approved",
            )
        )
        member = await session.scalar(
            select(PayrollRunMemberRecord).where(
                PayrollRunMemberRecord.company_id == context.company.id,
                PayrollRunMemberRecord.run_id == run_id,
                PayrollRunMemberRecord.employee_id == employee_id,
                PayrollRunMemberRecord.disposition == "ready",
            )
        )
        if (
            run is None
            or member is None
            or member.gross_result_id is None
            or member.tax_result_id is None
        ):
            raise PayrollConflictError(
                "approved complete Employee Payroll evidence is required"
            )
        gross = await session.scalar(
            select(PayrollGrossCalculationResultRecord).where(
                PayrollGrossCalculationResultRecord.company_id == context.company.id,
                PayrollGrossCalculationResultRecord.id == member.gross_result_id,
                PayrollGrossCalculationResultRecord.employee_id == employee_id,
                PayrollGrossCalculationResultRecord.lifecycle == "approved",
            )
        )
        tax = await session.scalar(
            select(PayrollTaxDeductionResultRecord).where(
                PayrollTaxDeductionResultRecord.company_id == context.company.id,
                PayrollTaxDeductionResultRecord.id == member.tax_result_id,
                PayrollTaxDeductionResultRecord.employee_id == employee_id,
                PayrollTaxDeductionResultRecord.lifecycle == "approved",
            )
        )
        if (
            gross is None
            or tax is None
            or tax.gross_result_id != gross.id
            or tax.gross_calculation_digest != gross.calculation_digest
            or gross.currency != tax.currency
            or tax.currency != run.currency
        ):
            raise PayrollConflictError(
                "Payroll result lineage is missing, conflicting, or unapproved"
            )
        if (
            member.gross_result_digest != gross.calculation_digest
            or member.tax_result_digest != tax.calculation_digest
        ):
            raise PayrollConflictError("Payroll run membership digests do not verify")
        adjustment = None
        if adjustment_result_id is not None:
            adjustment = await session.scalar(
                select(PayrollAdjustmentResultRecord).where(
                    PayrollAdjustmentResultRecord.company_id == context.company.id,
                    PayrollAdjustmentResultRecord.id == adjustment_result_id,
                    PayrollAdjustmentResultRecord.employee_id == employee_id,
                    PayrollAdjustmentResultRecord.lifecycle
                    == "applied_to_successor_authority",
                )
            )
            if adjustment is None:
                raise PayrollConflictError("applied adjustment evidence is required")
        reporting = None
        if reporting_snapshot_id is not None:
            reporting = await session.scalar(
                select(PayrollReportingSnapshotRecord).where(
                    PayrollReportingSnapshotRecord.company_id == context.company.id,
                    PayrollReportingSnapshotRecord.id == reporting_snapshot_id,
                    PayrollReportingSnapshotRecord.employee_id == employee_id,
                    PayrollReportingSnapshotRecord.period_kind == "year",
                    PayrollReportingSnapshotRecord.state == "authoritative",
                )
            )
            if (
                reporting is None
                or reporting.currency != run.currency
                or reporting.period_end < gross.period_end
            ):
                raise PayrollConflictError(
                    "authoritative Employee YTD reporting evidence is required"
                )
        payment_status, payment_digest, masked_method = await self._payment(
            session, run, employee_id
        )
        content: dict[str, object] = {
            "period_start": gross.period_start.isoformat(),
            "period_end": gross.period_end.isoformat(),
            "earnings": gross.earning_components,
            "gross_pay": str(tax.gross_pay),
            "employee_taxes": str(tax.employee_tax_total),
            "employee_deductions": str(tax.employee_deduction_total),
            "net_pay": str(tax.net_pay_candidate),
            "payment_method": masked_method,
        }
        ytd_status = "unavailable"
        if reporting is not None:
            content["ytd"] = reporting.totals
            ytd_status = "authoritative"
        economic = {
            "company_id": str(run.company_id),
            "employee_id": str(employee_id),
            "pay_period_id": str(run.pay_period_id),
            "run_id": str(run.id),
            "run_digest": run.run_digest,
            "gross_result_id": str(gross.id),
            "gross_digest": gross.calculation_digest,
            "tax_result_id": str(tax.id),
            "tax_digest": tax.calculation_digest,
            "adjustment_result_id": str(adjustment.id) if adjustment else None,
            "adjustment_digest": adjustment.calculation_digest if adjustment else None,
            "supersedes_statement_id": str(supersedes_statement_id)
            if supersedes_statement_id
            else None,
            "currency": run.currency,
            "payment_status": payment_status,
            "payment_evidence_digest": payment_digest,
            "content": content,
            "ytd_status": ytd_status,
            "definition_version": PAYSTATEMENT_VERSION,
        }
        if reporting is not None:
            economic["reporting_snapshot_id"] = str(reporting.id)
            economic["reporting_digest"] = reporting.report_digest
        digest = canonical_digest(economic)
        identity = f"payroll-pay-statement:{digest}"
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": identity},
        )
        existing = await session.scalar(
            select(PayrollPayStatementRecord).where(
                PayrollPayStatementRecord.company_id == run.company_id,
                PayrollPayStatementRecord.statement_identity == identity,
            )
        )
        if existing:
            return existing
        latest = await session.scalar(
            select(PayrollPayStatementRecord)
            .where(
                PayrollPayStatementRecord.company_id == run.company_id,
                PayrollPayStatementRecord.employee_id == employee_id,
                PayrollPayStatementRecord.pay_period_id == run.pay_period_id,
                PayrollPayStatementRecord.lifecycle.in_(("created", "issued")),
            )
            .order_by(PayrollPayStatementRecord.statement_version.desc())
            .with_for_update()
        )
        if latest is not None and (
            supersedes_statement_id != latest.id
            or latest.lifecycle != "issued"
            or (adjustment is None and reporting is None)
        ):
            raise PayrollConflictError(
                "changed statement evidence requires explicit successor authority"
            )
        value = PayrollPayStatementRecord(
            company_id=run.company_id,
            employee_id=employee_id,
            pay_period_id=run.pay_period_id,
            run_id=run.id,
            run_digest=run.run_digest,
            gross_result_id=gross.id,
            gross_result_digest=gross.calculation_digest,
            tax_result_id=tax.id,
            tax_result_digest=tax.calculation_digest,
            adjustment_result_id=adjustment.id if adjustment else None,
            adjustment_digest=adjustment.calculation_digest if adjustment else None,
            reporting_snapshot_id=reporting.id if reporting else None,
            reporting_digest=reporting.report_digest if reporting else None,
            statement_version=(latest.statement_version + 1 if latest else 1),
            definition_version=PAYSTATEMENT_VERSION,
            currency=run.currency,
            payment_status=payment_status,
            payment_evidence_digest=payment_digest,
            content=content,
            ytd_status=ytd_status,
            statement_identity=identity,
            statement_digest=digest,
            lifecycle="created",
            supersedes_statement_id=latest.id if latest else None,
            created_by_user_id=context.user.id,
        )
        if latest is not None:
            latest.lifecycle = "superseded"
        session.add(value)
        await session.flush()
        self._stage(
            session, context, value, EventType.PAYROLL_STATEMENT_CREATED, "created"
        )
        await session.commit()
        return value

    async def issue(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        statement_id: UUID,
    ) -> PayrollPayStatementRecord:
        self._require(context, PayrollPermission.STATEMENT_MANAGE)
        value = await self._statement(
            session, context.company.id, statement_id, lock=True
        )
        if value.lifecycle == "issued":
            return value
        if value.lifecycle != "created":
            raise PayrollConflictError("created statement is required")
        value.lifecycle, value.issued_by_user_id, value.issued_at = (
            "issued",
            context.user.id,
            datetime.now(timezone.utc),
        )
        self._stage(
            session, context, value, EventType.PAYROLL_STATEMENT_ISSUED, "issued"
        )
        await session.commit()
        return value

    async def own(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        statement_id: UUID,
    ) -> PayStatementView:
        self._require(context, PayrollPermission.STATEMENT_OWN_READ)
        employee = await session.scalar(
            select(Employee).where(
                Employee.company_id == context.company.id,
                Employee.membership_id == context.membership.id,
                Employee.status == "active",
            )
        )
        if employee is None:
            raise PayrollAuthorizationError(
                "authenticated membership is not linked to an active Employee"
            )
        value = await self._statement(session, context.company.id, statement_id)
        if value.employee_id != employee.id or value.lifecycle != "issued":
            raise PayrollAuthorizationError("statement access denied")
        self._stage(
            session, context, value, EventType.PAYROLL_STATEMENT_ACCESSED, "accessed"
        )
        await session.commit()
        return self._view(value)

    async def list_own(
        self, session: AsyncSession, *, context: AuthorizationContext
    ) -> tuple[PayStatementView, ...]:
        self._require(context, PayrollPermission.STATEMENT_OWN_READ)
        employee = await session.scalar(
            select(Employee).where(
                Employee.company_id == context.company.id,
                Employee.membership_id == context.membership.id,
                Employee.status == "active",
            )
        )
        if employee is None:
            raise PayrollAuthorizationError(
                "authenticated membership is not linked to an active Employee"
            )
        values = tuple(
            (
                await session.scalars(
                    select(PayrollPayStatementRecord)
                    .where(
                        PayrollPayStatementRecord.company_id == context.company.id,
                        PayrollPayStatementRecord.employee_id == employee.id,
                        PayrollPayStatementRecord.lifecycle == "issued",
                    )
                    .order_by(PayrollPayStatementRecord.created_at.desc())
                )
            ).all()
        )
        return tuple(self._view(value) for value in values)

    async def administrative(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        statement_id: UUID,
    ) -> PayStatementView:
        self._require(context, PayrollPermission.STATEMENT_READ)
        return self._view(
            await self._statement(session, context.company.id, statement_id)
        )

    async def _payment(
        self, session: AsyncSession, run: PayrollRunRecord, employee_id: UUID
    ) -> tuple[str, str | None, str | None]:
        instruction = await session.scalar(
            select(PayrollPaymentInstructionRecord)
            .join(
                PayrollPaymentReleaseRecord,
                PayrollPaymentReleaseRecord.id
                == PayrollPaymentInstructionRecord.release_id,
            )
            .where(
                PayrollPaymentInstructionRecord.company_id == run.company_id,
                PayrollPaymentReleaseRecord.payroll_run_id == run.id,
                PayrollPaymentInstructionRecord.employee_id == employee_id,
            )
        )
        if instruction is None:
            return "not_available", None, None
        item = await session.scalar(
            select(PayrollPaymentExecutionItemRecord)
            .join(
                PayrollPaymentExecutionRecord,
                PayrollPaymentExecutionRecord.id
                == PayrollPaymentExecutionItemRecord.execution_id,
            )
            .where(PayrollPaymentExecutionItemRecord.instruction_id == instruction.id)
        )
        status = (
            "pending"
            if item is None
            or item.lifecycle
            in {"authorized", "submitted", "acknowledged", "settlement_pending"}
            else "settled"
            if item.lifecycle == "settled"
            else "failed"
            if item.lifecycle in {"rejected", "failed"}
            else "unresolved"
        )
        digest = canonical_digest(
            {
                "instruction_digest": instruction.instruction_digest,
                "item_evidence_digest": item.evidence_digest if item else None,
                "status": status,
            }
        )
        return status, digest, instruction.method_type

    async def _statement(
        self,
        session: AsyncSession,
        company_id: UUID,
        statement_id: UUID,
        *,
        lock: bool = False,
    ) -> PayrollPayStatementRecord:
        query = select(PayrollPayStatementRecord).where(
            PayrollPayStatementRecord.company_id == company_id,
            PayrollPayStatementRecord.id == statement_id,
        )
        value = await session.scalar(query.with_for_update() if lock else query)
        if value is None:
            raise PayrollConflictError("pay statement was not found")
        return value

    @staticmethod
    def _view(value: PayrollPayStatementRecord) -> PayStatementView:
        return PayStatementView(
            value.id,
            value.employee_id,
            value.pay_period_id,
            value.statement_version,
            value.currency,
            value.payment_status,
            value.ytd_status,
            value.lifecycle,
            value.content,
            value.statement_digest,
        )

    @staticmethod
    def _require(context: AuthorizationContext, permission: str) -> None:
        if not context.has_permission(permission):
            raise PayrollAuthorizationError("pay statement permission denied")

    def _stage(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        value: PayrollPayStatementRecord,
        event: EventType,
        state: str,
    ) -> None:
        details: dict[str, object] = {
            "statement_id": str(value.id),
            "statement_digest": value.statement_digest,
            "employee_id": str(value.employee_id),
            "pay_period_id": str(value.pay_period_id),
            "lifecycle": value.lifecycle,
            "state": state,
        }
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=event,
                entity_type="payroll_pay_statement",
                entity_id=value.id,
                company_id=value.company_id,
                user_id=context.user.id,
                payload=details,
            ),
        )
        self._audit.stage(
            session,
            AuditEntry(
                action=f"payroll.pay_statement.{state}",
                resource_type="payroll_pay_statement",
                actor_user_id=context.user.id,
                company_id=value.company_id,
                resource_id=value.id,
                details=details,
            ),
        )
