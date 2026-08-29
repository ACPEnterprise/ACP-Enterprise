"""Company-scoped Payroll interpretation boundary for native Accounting PostingFact."""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.errors import AccountingConflict, AccountingValidation
from app.accounting.posting.contracts import (
    PostingFact,
    PostingLeg,
    PostingRule,
    PostingSide,
)
from app.accounting.repository import accounting_repository
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, AuditService, audit_service
from app.platform.permissions.authorization import AuthorizationContext

from .contracts import PayrollAuthorizationError, PayrollConflictError, canonical_digest
from .models import (
    PayrollAccountingMappingVersion,
    PayrollAccountingPolicyVersion,
    PayrollAdjustmentApplicationRecord,
    PayrollAdjustmentResultRecord,
    PayrollPaymentExecutionEvidenceRecord,
    PayrollPaymentExecutionItemRecord,
    PayrollPaymentExecutionRecord,
    PayrollRemittanceEvidenceRecord,
    PayrollRemittanceInstructionRecord,
    PayrollRemittanceObligationRecord,
    PayrollRunMemberRecord,
    PayrollRunRecord,
)
from .permissions import PayrollPermission

POLICY_DEFINITION_VERSION = "payroll.accounting-policy.v1"
MAPPING_DEFINITION_VERSION = "payroll.accounting-mapping.v1"
ADAPTER_VERSION = "payroll.accounting-posting-adapter.v1"


class PayrollRecognitionEvent(StrEnum):
    PAYROLL_ACCRUAL = "payroll_accrual"
    PAYMENT_RELEASE = "payment_release"
    WAGE_SETTLEMENT = "wage_settlement"
    TAX_REMITTANCE = "tax_remittance"
    DEDUCTION_REMITTANCE = "deduction_remittance"
    RETURN_ADJUSTMENT = "return_adjustment"
    ADJUSTMENT_APPLIED = "adjustment_applied"


class PayrollAccountingComponent(StrEnum):
    GROSS_WAGES = "gross_wages"
    EMPLOYEE_TAX_WITHHOLDING = "employee_tax_withholding"
    EMPLOYEE_DEDUCTION_PAYABLE = "employee_deduction_payable"
    EMPLOYER_PAYROLL_TAX_EXPENSE = "employer_payroll_tax_expense"
    EMPLOYER_PAYROLL_TAX_LIABILITY = "employer_payroll_tax_liability"
    EMPLOYER_CONTRIBUTION_EXPENSE = "employer_contribution_expense"
    EMPLOYER_CONTRIBUTION_LIABILITY = "employer_contribution_liability"
    NET_PAY_PAYABLE = "net_pay_payable"
    NET_PAY_LIABILITY_SETTLEMENT = "net_pay_liability_settlement"
    WAGE_SETTLEMENT = "wage_settlement"
    TAX_REMITTANCE = "tax_remittance"
    DEDUCTION_REMITTANCE = "deduction_remittance"
    TAX_LIABILITY_SETTLEMENT = "tax_liability_settlement"
    DEDUCTION_LIABILITY_SETTLEMENT = "deduction_liability_settlement"
    BENEFIT_LIABILITY_SETTLEMENT = "benefit_liability_settlement"
    CASH_CLEARING = "cash_clearing"
    ADJUSTMENT_DEBIT = "adjustment_debit"
    ADJUSTMENT_CREDIT = "adjustment_credit"


@dataclass(frozen=True)
class DraftPayrollAccountingPolicy:
    policy_version: int
    recognition_event: PayrollRecognitionEvent
    currency: str
    effective_start: date
    effective_end: date | None
    decision_evidence_digest: str


@dataclass(frozen=True)
class DraftPayrollAccountingMapping:
    mapping_version: int
    recognition_event: PayrollRecognitionEvent
    component: PayrollAccountingComponent
    posting_side: PostingSide
    account_id: UUID
    currency: str
    effective_start: date
    effective_end: date | None
    approval_evidence_digest: str


@dataclass(frozen=True)
class PayrollPostingFactCandidate:
    fact: PostingFact
    policy_id: UUID
    policy_digest: str
    mapping_ids: tuple[UUID, ...]
    mapping_digests: tuple[str, ...]
    posting_rule: PostingRule
    candidate_identity: str

    def verify(self) -> None:
        evidence = canonical_digest({"policy_id": str(self.policy_id), "policy_digest": self.policy_digest, "mapping_ids": tuple(str(value) for value in self.mapping_ids), "mapping_digests": self.mapping_digests, "fact_components": {key: str(value) for key, value in sorted(self.fact.components.items())}, "source_id": str(self.fact.source_id), "source_event_id": str(self.fact.source_event_id), "event_type": self.fact.event_type, "effective_date": self.fact.effective_date.isoformat(), "currency": self.fact.currency, "adapter_version": ADAPTER_VERSION})
        identity_digest = canonical_digest({"fact_digest": self.fact.canonical_digest(), "evidence_digest": self.fact.evidence_digest})
        if evidence != self.fact.evidence_digest or self.candidate_identity != f"payroll-posting-fact:{identity_digest}":
            raise PayrollConflictError("Payroll Accounting PostingFact candidate is invalid")


class PayrollAccountingPostingService:
    def __init__(self, *, audit: AuditService = audit_service) -> None:
        self._audit = audit

    async def create_policy(self, session: AsyncSession, *, context: AuthorizationContext, draft: DraftPayrollAccountingPolicy) -> PayrollAccountingPolicyVersion:
        self._require(context, PayrollPermission.ACCOUNTING_POLICY_MANAGE)
        self._validate_interval(draft.effective_start, draft.effective_end)
        content = {"company_id": str(context.company.id), "version": draft.policy_version, "definition_version": POLICY_DEFINITION_VERSION, "recognition_event": draft.recognition_event.value, "currency": draft.currency, "effective_start": draft.effective_start.isoformat(), "effective_end": draft.effective_end.isoformat() if draft.effective_end else None, "decision_evidence_digest": draft.decision_evidence_digest}
        value = PayrollAccountingPolicyVersion(company_id=context.company.id, policy_version=draft.policy_version, definition_version=POLICY_DEFINITION_VERSION, recognition_event=draft.recognition_event.value, currency=draft.currency, effective_start=draft.effective_start, effective_end=draft.effective_end, lifecycle="draft", decision_evidence_digest=draft.decision_evidence_digest, policy_digest=canonical_digest(content), created_by_user_id=context.user.id)
        session.add(value)
        await session.flush()
        self._stage(session, context, "payroll_accounting_policy", value.id, value.policy_digest, draft.recognition_event.value, "draft", EventType.PAYROLL_ACCOUNTING_POLICY_CREATED)
        await session.commit()
        return value

    async def approve_policy(self, session: AsyncSession, *, context: AuthorizationContext, policy_id: UUID) -> PayrollAccountingPolicyVersion:
        self._require(context, PayrollPermission.ACCOUNTING_POLICY_APPROVE)
        value = await session.scalar(select(PayrollAccountingPolicyVersion).where(PayrollAccountingPolicyVersion.company_id == context.company.id, PayrollAccountingPolicyVersion.id == policy_id).with_for_update())
        if value is None or value.lifecycle != "draft":
            raise PayrollConflictError("draft Payroll Accounting policy is unavailable")
        if value.created_by_user_id == context.user.id:
            raise PayrollAuthorizationError("Payroll Accounting policy drafter cannot self-approve")
        if await self._policy_overlaps(session, value):
            raise PayrollConflictError("approved Payroll Accounting policies overlap")
        value.lifecycle, value.approved_by_user_id, value.approved_at = "approved", context.user.id, datetime.now(timezone.utc)
        self._stage(session, context, "payroll_accounting_policy", value.id, value.policy_digest, value.recognition_event, value.lifecycle, EventType.PAYROLL_ACCOUNTING_POLICY_APPROVED)
        await session.commit()
        return value

    async def create_mapping(self, session: AsyncSession, *, context: AuthorizationContext, draft: DraftPayrollAccountingMapping) -> PayrollAccountingMappingVersion:
        self._require(context, PayrollPermission.ACCOUNTING_MAPPING_MANAGE)
        self._validate_interval(draft.effective_start, draft.effective_end)
        account = await accounting_repository.account(session, context.company.id, draft.account_id)
        if account is None or account.status != "active":
            raise PayrollConflictError("active native Accounting account is required")
        content = {"company_id": str(context.company.id), "version": draft.mapping_version, "definition_version": MAPPING_DEFINITION_VERSION, "recognition_event": draft.recognition_event.value, "component": draft.component.value, "posting_side": draft.posting_side.value, "account_id": str(draft.account_id), "currency": draft.currency, "effective_start": draft.effective_start.isoformat(), "effective_end": draft.effective_end.isoformat() if draft.effective_end else None, "approval_evidence_digest": draft.approval_evidence_digest}
        value = PayrollAccountingMappingVersion(company_id=context.company.id, mapping_version=draft.mapping_version, definition_version=MAPPING_DEFINITION_VERSION, recognition_event=draft.recognition_event.value, component=draft.component.value, posting_side=draft.posting_side.value, account_id=draft.account_id, currency=draft.currency, effective_start=draft.effective_start, effective_end=draft.effective_end, lifecycle="draft", approval_evidence_digest=draft.approval_evidence_digest, mapping_digest=canonical_digest(content), created_by_user_id=context.user.id)
        session.add(value)
        await session.flush()
        self._stage(session, context, "payroll_accounting_mapping", value.id, value.mapping_digest, value.recognition_event, value.lifecycle, EventType.PAYROLL_ACCOUNTING_MAPPING_CREATED)
        await session.commit()
        return value

    async def approve_mapping(self, session: AsyncSession, *, context: AuthorizationContext, mapping_id: UUID) -> PayrollAccountingMappingVersion:
        self._require(context, PayrollPermission.ACCOUNTING_MAPPING_APPROVE)
        value = await session.scalar(select(PayrollAccountingMappingVersion).where(PayrollAccountingMappingVersion.company_id == context.company.id, PayrollAccountingMappingVersion.id == mapping_id).with_for_update())
        if value is None or value.lifecycle != "draft":
            raise PayrollConflictError("draft Payroll Accounting mapping is unavailable")
        if value.created_by_user_id == context.user.id:
            raise PayrollAuthorizationError("Payroll Accounting mapping drafter cannot self-approve")
        if await self._mapping_overlaps(session, value):
            raise PayrollConflictError("approved Payroll Accounting mappings overlap")
        value.lifecycle, value.approved_by_user_id, value.approved_at = "approved", context.user.id, datetime.now(timezone.utc)
        self._stage(session, context, "payroll_accounting_mapping", value.id, value.mapping_digest, value.recognition_event, value.lifecycle, EventType.PAYROLL_ACCOUNTING_MAPPING_APPROVED)
        await session.commit()
        return value

    async def prepare_accrual(self, session: AsyncSession, *, context: AuthorizationContext, payroll_run_id: UUID, effective_date: date, period_id: UUID) -> PayrollPostingFactCandidate:
        self._require(context, PayrollPermission.ACCOUNTING_PREPARE)
        run = await session.scalar(select(PayrollRunRecord).where(PayrollRunRecord.company_id == context.company.id, PayrollRunRecord.id == payroll_run_id, PayrollRunRecord.lifecycle == "approved"))
        if run is None:
            raise PayrollConflictError("approved Payroll run is required")
        members = tuple((await session.scalars(select(PayrollRunMemberRecord).where(PayrollRunMemberRecord.run_id == run.id))).all())
        if any(item.disposition == "ready" and (item.tax_result_id is None or item.tax_result_digest is None) for item in members):
            raise PayrollConflictError("ready Payroll population evidence is incomplete")
        components = {PayrollAccountingComponent.GROSS_WAGES.value: run.aggregate_gross, PayrollAccountingComponent.EMPLOYEE_TAX_WITHHOLDING.value: run.aggregate_employee_taxes, PayrollAccountingComponent.EMPLOYEE_DEDUCTION_PAYABLE.value: run.aggregate_employee_deductions, PayrollAccountingComponent.NET_PAY_PAYABLE.value: run.aggregate_net_pay}
        if run.aggregate_employer_contributions:
            components[PayrollAccountingComponent.EMPLOYER_CONTRIBUTION_EXPENSE.value] = run.aggregate_employer_contributions
            components[PayrollAccountingComponent.EMPLOYER_CONTRIBUTION_LIABILITY.value] = run.aggregate_employer_contributions
        return await self._prepare(session, context, PayrollRecognitionEvent.PAYROLL_ACCRUAL, run.id, run.id, run.run_digest, run.currency, components, effective_date, run.assembled_at, period_id)

    async def prepare_wage_settlement(self, session: AsyncSession, *, context: AuthorizationContext, execution_id: UUID, effective_date: date, period_id: UUID) -> PayrollPostingFactCandidate:
        self._require(context, PayrollPermission.ACCOUNTING_PREPARE)
        execution = await session.scalar(select(PayrollPaymentExecutionRecord).where(PayrollPaymentExecutionRecord.company_id == context.company.id, PayrollPaymentExecutionRecord.id == execution_id, PayrollPaymentExecutionRecord.lifecycle.in_(("settled", "partially_settled"))))
        if execution is None:
            raise PayrollConflictError("explicit settled payment execution evidence is required")
        items = tuple((await session.scalars(select(PayrollPaymentExecutionItemRecord).where(PayrollPaymentExecutionItemRecord.execution_id == execution.id, PayrollPaymentExecutionItemRecord.lifecycle == "settled"))).all())
        if not items or any(item.evidence_digest is None for item in items):
            raise PayrollConflictError("settled instruction evidence is incomplete")
        evidence = await session.scalar(select(PayrollPaymentExecutionEvidenceRecord).where(PayrollPaymentExecutionEvidenceRecord.execution_id == execution.id, PayrollPaymentExecutionEvidenceRecord.evidence_type == "settlement").order_by(PayrollPaymentExecutionEvidenceRecord.occurred_at.desc()))
        if evidence is None:
            raise PayrollConflictError("settlement authority is unavailable")
        amount = sum((item.amount for item in items), Decimal(0))
        components = {PayrollAccountingComponent.NET_PAY_LIABILITY_SETTLEMENT.value: amount, PayrollAccountingComponent.WAGE_SETTLEMENT.value: amount}
        return await self._prepare(session, context, PayrollRecognitionEvent.WAGE_SETTLEMENT, execution.payroll_run_id, evidence.id, canonical_digest({"execution_digest": execution.execution_digest, "settlement_digest": evidence.evidence_digest, "instruction_digests": tuple(sorted(item.evidence_digest or "" for item in items))}), execution.currency, components, effective_date, evidence.occurred_at, period_id)

    async def prepare_remittance_settlement(self, session: AsyncSession, *, context: AuthorizationContext, obligation_id: UUID, effective_date: date, period_id: UUID) -> PayrollPostingFactCandidate:
        """Project only explicitly settled remittance evidence; acknowledgement is insufficient."""
        self._require(context, PayrollPermission.ACCOUNTING_PREPARE)
        obligation = await session.scalar(select(PayrollRemittanceObligationRecord).where(PayrollRemittanceObligationRecord.company_id == context.company.id, PayrollRemittanceObligationRecord.id == obligation_id, PayrollRemittanceObligationRecord.lifecycle.in_(("settled", "partially_settled"))))
        if obligation is None or obligation.settled_amount <= 0:
            raise PayrollConflictError("explicit remittance settlement authority is required")
        instruction = await session.scalar(select(PayrollRemittanceInstructionRecord).where(PayrollRemittanceInstructionRecord.company_id == context.company.id, PayrollRemittanceInstructionRecord.obligation_id == obligation.id))
        if instruction is None:
            raise PayrollConflictError("remittance instruction authority is unavailable")
        evidence = tuple((await session.scalars(select(PayrollRemittanceEvidenceRecord).where(PayrollRemittanceEvidenceRecord.instruction_id == instruction.id, PayrollRemittanceEvidenceRecord.evidence_type == "settlement").order_by(PayrollRemittanceEvidenceRecord.occurred_at))).all())
        proven = sum((item.amount or Decimal(0) for item in evidence), Decimal(0))
        if not evidence or proven != obligation.settled_amount:
            raise PayrollConflictError("remittance settlement evidence does not reconcile")
        tax = obligation.classification in {"employee_tax_withholding", "employer_payroll_tax"}
        benefit = obligation.classification == "employer_benefit_contribution"
        event = PayrollRecognitionEvent.TAX_REMITTANCE if tax else PayrollRecognitionEvent.DEDUCTION_REMITTANCE
        liability = PayrollAccountingComponent.TAX_LIABILITY_SETTLEMENT if tax else PayrollAccountingComponent.BENEFIT_LIABILITY_SETTLEMENT if benefit else PayrollAccountingComponent.DEDUCTION_LIABILITY_SETTLEMENT
        components = {liability.value: proven, PayrollAccountingComponent.CASH_CLEARING.value: proven}
        digest = canonical_digest({"obligation_digest": obligation.obligation_digest, "instruction_digest": instruction.instruction_digest, "settlement_evidence": tuple(item.evidence_digest for item in evidence), "settled_amount": str(proven)})
        return await self._prepare(session, context, event, obligation.payroll_run_id, instruction.id, digest, obligation.currency, components, effective_date, evidence[-1].occurred_at, period_id)

    async def prepare_adjustment(self, session: AsyncSession, *, context: AuthorizationContext, application_id: UUID, effective_date: date, period_id: UUID) -> PayrollPostingFactCandidate:
        """Project an applied signed adjustment as an incremental, never historical, fact."""
        self._require(context, PayrollPermission.ACCOUNTING_PREPARE)
        application = await session.scalar(select(PayrollAdjustmentApplicationRecord).where(PayrollAdjustmentApplicationRecord.company_id == context.company.id, PayrollAdjustmentApplicationRecord.id == application_id))
        if application is None or application.purpose != "accounting_adjustment":
            raise PayrollConflictError("applied Accounting adjustment authority is required")
        result = await session.scalar(select(PayrollAdjustmentResultRecord).where(PayrollAdjustmentResultRecord.company_id == context.company.id, PayrollAdjustmentResultRecord.id == application.result_id, PayrollAdjustmentResultRecord.lifecycle == "applied_to_successor_authority"))
        if result is None or result.calculation_digest != application.result_digest:
            raise PayrollConflictError("adjustment result authority does not verify")
        debit = sum((Decimal(str(item["delta"])) for item in application.authorized_components if Decimal(str(item["delta"])) > 0), Decimal(0))
        credit = -sum((Decimal(str(item["delta"])) for item in application.authorized_components if Decimal(str(item["delta"])) < 0), Decimal(0))
        amount = debit or credit
        if amount <= 0 or debit and credit and debit != credit:
            raise PayrollConflictError("Accounting adjustment deltas do not form a deterministic balanced authority")
        components = {PayrollAccountingComponent.ADJUSTMENT_DEBIT.value: amount, PayrollAccountingComponent.ADJUSTMENT_CREDIT.value: amount}
        return await self._prepare(session, context, PayrollRecognitionEvent.ADJUSTMENT_APPLIED, result.id, application.id, application.application_digest, result.currency, components, effective_date, application.applied_at, period_id)

    async def _prepare(self, session: AsyncSession, context: AuthorizationContext, event: PayrollRecognitionEvent, source_id: UUID, source_event_id: UUID, source_digest: str, currency: str, components: dict[str, Decimal], effective_date: date, occurred_at: datetime, period_id: UUID) -> PayrollPostingFactCandidate:
        period = await accounting_repository.period(session, context.company.id, period_id)
        if period is None or not period.start_date <= effective_date <= period.end_date:
            raise AccountingValidation("Payroll Accounting date is outside the selected period")
        if period.status not in {"open", "reopened"}:
            raise AccountingConflict("selected Accounting period does not accept Payroll facts")
        policy = await self._resolve_policy(session, context.company.id, event, effective_date)
        if policy.currency != currency:
            raise PayrollConflictError("Payroll Accounting policy currency mismatch")
        nonzero = {key: Decimal(value) for key, value in components.items() if Decimal(value) != 0}
        mappings = await self._resolve_mappings(session, context.company.id, event, tuple(nonzero), effective_date, currency)
        debits = sum((nonzero[item.component] for item in mappings if item.posting_side == "debit"), Decimal(0))
        credits = sum((nonzero[item.component] for item in mappings if item.posting_side == "credit"), Decimal(0))
        if debits != credits or not nonzero:
            raise PayrollConflictError("Payroll Accounting components do not balance")
        event_type = f"payroll.{event.value}"
        evidence_digest = canonical_digest({"policy_id": str(policy.id), "policy_digest": policy.policy_digest, "mapping_ids": tuple(str(value.id) for value in mappings), "mapping_digests": tuple(value.mapping_digest for value in mappings), "fact_components": {key: str(value) for key, value in sorted(nonzero.items())}, "source_id": str(source_id), "source_event_id": str(source_event_id), "event_type": event_type, "effective_date": effective_date.isoformat(), "currency": currency, "adapter_version": ADAPTER_VERSION})
        fact = PostingFact("1.0", context.company.id, None, source_event_id, "payroll", source_id, event_type, effective_date, occurred_at, currency, nonzero, evidence_digest)
        legs = tuple(PostingLeg(item.component, item.account_id, PostingSide(item.posting_side), item.component) for item in mappings)
        mapping_set_digest = canonical_digest(tuple(value.mapping_digest for value in mappings))
        rule = PostingRule(context.company.id, fact.event_type, f"payroll:{policy.policy_digest[:24]}:{mapping_set_digest[:24]}", policy.effective_start, policy.effective_end, policy.approved_at or datetime.now(timezone.utc), policy.approved_by_user_id or policy.created_by_user_id, legs)
        identity_digest = canonical_digest({"fact_digest": fact.canonical_digest(), "evidence_digest": fact.evidence_digest})
        result = PayrollPostingFactCandidate(fact, policy.id, policy.policy_digest, tuple(value.id for value in mappings), tuple(value.mapping_digest for value in mappings), rule, f"payroll-posting-fact:{identity_digest}")
        result.verify()
        self._stage(session, context, "payroll_accounting_fact", source_event_id, fact.evidence_digest, event.value, "prepared", EventType.PAYROLL_ACCOUNTING_FACT_PREPARED)
        await session.commit()
        return result

    async def _resolve_policy(self, session: AsyncSession, company_id: UUID, event: PayrollRecognitionEvent, effective_date: date) -> PayrollAccountingPolicyVersion:
        values = tuple((await session.scalars(select(PayrollAccountingPolicyVersion).where(PayrollAccountingPolicyVersion.company_id == company_id, PayrollAccountingPolicyVersion.recognition_event == event.value, PayrollAccountingPolicyVersion.effective_start <= effective_date, (PayrollAccountingPolicyVersion.effective_end.is_(None) | (PayrollAccountingPolicyVersion.effective_end > effective_date)), PayrollAccountingPolicyVersion.lifecycle == "approved"))).all())
        if len(values) != 1:
            raise PayrollConflictError("exactly one approved effective Payroll Accounting policy is required")
        return values[0]

    async def _resolve_mappings(self, session: AsyncSession, company_id: UUID, event: PayrollRecognitionEvent, components: tuple[str, ...], effective_date: date, currency: str) -> tuple[PayrollAccountingMappingVersion, ...]:
        values = tuple((await session.scalars(select(PayrollAccountingMappingVersion).where(PayrollAccountingMappingVersion.company_id == company_id, PayrollAccountingMappingVersion.recognition_event == event.value, PayrollAccountingMappingVersion.component.in_(components), PayrollAccountingMappingVersion.effective_start <= effective_date, (PayrollAccountingMappingVersion.effective_end.is_(None) | (PayrollAccountingMappingVersion.effective_end > effective_date)), PayrollAccountingMappingVersion.lifecycle == "approved"))).all())
        grouped = {component: tuple(item for item in values if item.component == component) for component in components}
        if any(len(items) != 1 for items in grouped.values()):
            raise PayrollConflictError("complete unambiguous Payroll Accounting mappings are required")
        ordered = tuple(grouped[key][0] for key in sorted(grouped))
        if any(item.currency != currency for item in ordered):
            raise PayrollConflictError("Payroll Accounting mapping currency mismatch")
        for item in ordered:
            account = await accounting_repository.account(session, company_id, item.account_id)
            if account is None or account.status != "active" or not account.effective_from <= effective_date or account.effective_to is not None and account.effective_to <= effective_date:
                raise PayrollConflictError("mapped Accounting account is not effective")
        return ordered

    async def _policy_overlaps(self, session: AsyncSession, value: PayrollAccountingPolicyVersion) -> bool:
        values = tuple((await session.scalars(select(PayrollAccountingPolicyVersion).where(PayrollAccountingPolicyVersion.company_id == value.company_id, PayrollAccountingPolicyVersion.recognition_event == value.recognition_event, PayrollAccountingPolicyVersion.lifecycle == "approved"))).all())
        return any(self._overlap(value.effective_start, value.effective_end, item.effective_start, item.effective_end) for item in values)

    async def _mapping_overlaps(self, session: AsyncSession, value: PayrollAccountingMappingVersion) -> bool:
        values = tuple((await session.scalars(select(PayrollAccountingMappingVersion).where(PayrollAccountingMappingVersion.company_id == value.company_id, PayrollAccountingMappingVersion.recognition_event == value.recognition_event, PayrollAccountingMappingVersion.component == value.component, PayrollAccountingMappingVersion.lifecycle == "approved"))).all())
        return any(self._overlap(value.effective_start, value.effective_end, item.effective_start, item.effective_end) for item in values)

    @staticmethod
    def _overlap(a_start: date, a_end: date | None, b_start: date, b_end: date | None) -> bool:
        return a_start < (b_end or date.max) and b_start < (a_end or date.max)

    @staticmethod
    def _validate_interval(start: date, end: date | None) -> None:
        if end is not None and end <= start:
            raise PayrollConflictError("Payroll Accounting effective interval is invalid")

    @staticmethod
    def _require(context: AuthorizationContext, permission: str) -> None:
        if not context.has_permission(permission):
            raise PayrollAuthorizationError("Payroll Accounting permission denied")

    def _stage(self, session: AsyncSession, context: AuthorizationContext, resource: str, resource_id: UUID, digest: str, event: str, state: str, event_type: EventType) -> None:
        details: dict[str, object] = {"authority_id": str(resource_id), "digest": digest, "recognition_event": event, "state": state}
        BusinessEventService.stage(session, BusinessEventCreate(event_type=event_type, entity_type=resource, entity_id=resource_id, company_id=context.company.id, user_id=context.user.id, payload=details))
        self._audit.stage(session, AuditEntry(action=f"{resource}.{state}", resource_type=resource, actor_user_id=context.user.id, company_id=context.company.id, resource_id=resource_id, details=details))
