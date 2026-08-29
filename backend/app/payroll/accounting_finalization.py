"""Governed composition of Payroll PostingFacts with native Accounting Core."""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.posting.contracts import PostingOutcome, PostingReceipt, PostingSide
from app.accounting.posting.rules import PostingRuleRegistry
from app.accounting.posting.service import AutomatedPostingService
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, AuditService, audit_service
from app.platform.permissions.authorization import AuthorizationContext

from .accounting_posting import PayrollPostingFactCandidate
from .contracts import PayrollAuthorizationError, PayrollConflictError, canonical_digest
from .models import PayrollAccountingConsumptionRecord, PayrollRunRecord
from .permissions import PayrollPermission


@dataclass(frozen=True)
class PayrollAccountingReconciliation:
    payroll_run_id: UUID
    currency: str
    approved_net_pay: Decimal
    accrued: Decimal
    wage_settled: Decimal
    remittance_settled: Decimal
    outstanding_net_pay: Decimal
    disposition: str
    reconciliation_digest: str


class PayrollAccountingFinalizationService:
    """Durably consumes Payroll facts and delegates all journal governance."""

    def __init__(self, *, audit: AuditService = audit_service) -> None:
        self._audit = audit

    async def persist_candidate(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        candidate: PayrollPostingFactCandidate,
    ) -> PayrollAccountingConsumptionRecord:
        self._require(context, PayrollPermission.ACCOUNTING_PREPARE)
        candidate.verify()
        fact = candidate.fact
        if fact.company_id != context.company.id:
            raise PayrollConflictError("Payroll Accounting candidate is cross-Company")
        await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": candidate.candidate_identity})
        existing = await session.scalar(select(PayrollAccountingConsumptionRecord).where(PayrollAccountingConsumptionRecord.company_id == fact.company_id, PayrollAccountingConsumptionRecord.recognition_event == fact.event_type.removeprefix("payroll."), PayrollAccountingConsumptionRecord.source_event_id == fact.source_event_id))
        fact_digest = fact.canonical_digest()
        if existing:
            if existing.fact_digest != fact_digest or existing.candidate_identity != candidate.candidate_identity:
                raise PayrollConflictError("Payroll Accounting source consumption conflicts")
            return existing
        debits = sum((fact.components[leg.component] for leg in candidate.posting_rule.legs if leg.side is PostingSide.DEBIT), Decimal(0))
        record = PayrollAccountingConsumptionRecord(
            company_id=fact.company_id,
            recognition_event=fact.event_type.removeprefix("payroll."),
            source_type=fact.source_type,
            source_id=fact.source_id,
            source_event_id=fact.source_event_id,
            source_digest=fact.evidence_digest,
            fact_digest=fact_digest,
            candidate_identity=candidate.candidate_identity,
            amount=debits,
            currency=fact.currency,
            lifecycle="prepared",
            prepared_by_user_id=context.user.id,
        )
        session.add(record)
        await session.commit()
        return record

    async def post_candidate(
        self,
        session: AsyncSession,
        *,
        candidate: PayrollPostingFactCandidate,
        period_id: UUID,
        preparer: AuthorizationContext,
        approver: AuthorizationContext,
        poster: AuthorizationContext,
    ) -> PostingReceipt:
        consumption = await self.persist_candidate(session, context=preparer, candidate=candidate)
        if consumption.lifecycle == "posted":
            if consumption.journal_id is None or consumption.posted_at is None:
                raise PayrollConflictError("posted Payroll Accounting consumption is incomplete")
            return PostingReceipt(candidate.fact.company_id, candidate.fact.branch_id, candidate.fact.source_event_id, candidate.fact.source_type, candidate.fact.source_id, consumption.journal_id, consumption.journal_version, candidate.posting_rule.version, PostingOutcome.POSTED, candidate.fact.effective_date, consumption.posted_at)
        posting = AutomatedPostingService(rules=PostingRuleRegistry((candidate.posting_rule,)))
        receipt = await posting.post(session, fact=candidate.fact, period_id=period_id, preparer=preparer, approver=approver, poster=poster)
        value = await session.scalar(select(PayrollAccountingConsumptionRecord).where(PayrollAccountingConsumptionRecord.id == consumption.id).with_for_update())
        if value is None:
            raise PayrollConflictError("Payroll Accounting consumption disappeared")
        if value.journal_id not in {None, receipt.journal_id}:
            raise PayrollConflictError("Payroll Accounting journal linkage conflicts")
        value.lifecycle, value.journal_id, value.journal_version, value.posted_at = "posted", receipt.journal_id, receipt.journal_version, receipt.posted_at
        details: dict[str, object] = {"consumption_id": str(value.id), "fact_digest": value.fact_digest, "journal_id": str(receipt.journal_id), "recognition_event": value.recognition_event, "lifecycle": value.lifecycle}
        BusinessEventService.stage(session, BusinessEventCreate(event_type=EventType.PAYROLL_ACCOUNTING_FACT_POSTED, entity_type="payroll_accounting_consumption", entity_id=value.id, company_id=value.company_id, user_id=poster.user.id, payload=details))
        self._audit.stage(session, AuditEntry(action="payroll.accounting_fact.posted", resource_type="payroll_accounting_consumption", actor_user_id=poster.user.id, company_id=value.company_id, resource_id=value.id, details=details))
        await session.commit()
        return receipt

    async def reconciliation(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        payroll_run_id: UUID,
    ) -> PayrollAccountingReconciliation:
        self._require(context, PayrollPermission.ACCOUNTING_READ)
        run = await session.scalar(select(PayrollRunRecord).where(PayrollRunRecord.company_id == context.company.id, PayrollRunRecord.id == payroll_run_id, PayrollRunRecord.lifecycle == "approved"))
        if run is None:
            raise PayrollConflictError("approved Payroll run is required for reconciliation")
        rows = tuple((await session.scalars(select(PayrollAccountingConsumptionRecord).where(PayrollAccountingConsumptionRecord.company_id == context.company.id, PayrollAccountingConsumptionRecord.source_id == run.id, PayrollAccountingConsumptionRecord.lifecycle == "posted"))).all())
        accrued = sum((row.amount for row in rows if row.recognition_event == "payroll_accrual"), Decimal(0))
        wage = sum((row.amount for row in rows if row.recognition_event == "wage_settlement"), Decimal(0))
        remittance = sum((row.amount for row in rows if row.recognition_event in {"tax_remittance", "deduction_remittance"}), Decimal(0))
        outstanding = run.aggregate_net_pay - wage
        if outstanding < 0:
            raise PayrollConflictError("Payroll Accounting settlement exceeds approved net pay")
        disposition = "reconciled" if outstanding == 0 else "outstanding"
        digest = canonical_digest({"payroll_run_id": str(run.id), "run_digest": run.run_digest, "accrued": str(accrued), "wage_settled": str(wage), "remittance_settled": str(remittance), "outstanding_net_pay": str(outstanding), "currency": run.currency, "disposition": disposition})
        return PayrollAccountingReconciliation(run.id, run.currency, run.aggregate_net_pay, accrued, wage, remittance, outstanding, disposition, digest)

    @staticmethod
    def _require(context: AuthorizationContext, permission: str) -> None:
        if not context.has_permission(permission):
            raise PayrollAuthorizationError("Payroll Accounting permission denied")
