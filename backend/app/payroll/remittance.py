"""Provider-neutral Payroll liability remittance authority; never moves money."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, AuditService, audit_service
from app.platform.permissions.authorization import AuthorizationContext
from app.timekeeping.models import PayPeriod

from .contracts import PayrollAuthorizationError, PayrollConflictError, canonical_digest
from .models import (
    PayrollRemittanceDestinationRecord,
    PayrollRemittanceEvidenceRecord,
    PayrollRemittanceInstructionRecord,
    PayrollRemittanceObligationRecord,
    PayrollRemittancePolicyRecord,
    PayrollRemittanceReviewRecord,
    PayrollRunMemberRecord,
    PayrollRunRecord,
)
from .permissions import PayrollPermission

REMITTANCE_VERSION = "payroll.remittance-foundation.v1"


class RemittanceClassification(StrEnum):
    EMPLOYEE_TAX_WITHHOLDING = "employee_tax_withholding"
    EMPLOYER_PAYROLL_TAX = "employer_payroll_tax"
    EMPLOYEE_DEDUCTION = "employee_deduction"
    EMPLOYER_BENEFIT_CONTRIBUTION = "employer_benefit_contribution"
    OTHER_PAYROLL_LIABILITY = "other_payroll_liability"


class ScheduleState(StrEnum):
    READY = "ready"
    NOT_DUE = "not_due"
    DUE = "due"
    OVERDUE = "overdue"
    BLOCKED = "blocked"
    CONFLICTING = "conflicting"
    NOT_APPLICABLE = "not_applicable"


class ProviderState(StrEnum):
    ACKNOWLEDGED = "acknowledged"
    REJECTED = "rejected"
    PENDING = "pending"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class DraftRemittancePolicy:
    classification: RemittanceClassification
    version: int
    currency: str
    aggregation_permitted: bool
    due_days_after_period: int | None
    destination_required: bool
    accounting_consequence: str
    effective_start: date
    effective_end: date | None
    evidence_digest: str


@dataclass(frozen=True)
class DraftRemittanceDestination:
    destination_type: str
    jurisdiction_reference: str | None
    protected_reference: str
    masked_display: str
    effective_start: date
    effective_end: date | None


@dataclass(frozen=True)
class RemittanceProviderRequest:
    instruction_identity: str
    instruction_digest: str
    protected_destination_reference: str
    amount: Decimal
    currency: str
    idempotency_identity: str
    request_digest: str


@dataclass(frozen=True)
class RemittanceAcknowledgement:
    state: ProviderState
    provider_safe_reference: str
    request_digest: str
    response_digest: str
    acknowledged_at: datetime


class RemittanceProvider(Protocol):
    identity: str
    version: str

    async def submit(self, request: RemittanceProviderRequest) -> RemittanceAcknowledgement: ...


class SyntheticRemittanceProvider:
    identity = "synthetic.remittance-provider"
    version = "test.v1"

    def __init__(self, *, environment: str, state: ProviderState = ProviderState.ACKNOWLEDGED) -> None:
        if environment != "test":
            raise PayrollConflictError("synthetic remittance provider is test-only")
        self.state, self.calls = state, 0
        self._responses: dict[str, RemittanceAcknowledgement] = {}

    async def submit(self, request: RemittanceProviderRequest) -> RemittanceAcknowledgement:
        if request.idempotency_identity in self._responses:
            return self._responses[request.idempotency_identity]
        self.calls += 1
        reference = f"synthetic-remittance:{request.request_digest[:16]}"
        digest = canonical_digest({"state": self.state.value, "reference": reference, "request_digest": request.request_digest})
        value = RemittanceAcknowledgement(self.state, reference, request.request_digest, digest, datetime.now(timezone.utc))
        self._responses[request.idempotency_identity] = value
        return value


@dataclass(frozen=True)
class RemittanceReconciliation:
    source_total: Decimal
    obligation_total: Decimal
    instruction_total: Decimal
    settled: Decimal
    outstanding: Decimal
    disposition: str
    reconciliation_digest: str


@dataclass(frozen=True)
class RemittanceAccountingHandoff:
    obligation_id: UUID
    obligation_digest: str
    instruction_id: UUID
    settlement_evidence_digests: tuple[str, ...]
    settled_amount: Decimal
    currency: str
    recognition_event: str
    expense_recognition: bool = False


class PayrollRemittanceService:
    def __init__(self, *, audit: AuditService = audit_service) -> None:
        self._audit = audit

    async def create_policy(self, session: AsyncSession, *, context: AuthorizationContext, draft: DraftRemittancePolicy) -> PayrollRemittancePolicyRecord:
        self._require(context, PayrollPermission.REMITTANCE_MANAGE)
        if draft.version < 1 or draft.effective_end and draft.effective_end <= draft.effective_start or draft.due_days_after_period is not None and draft.due_days_after_period < 0:
            raise PayrollConflictError("remittance policy is invalid")
        content = {"company_id": str(context.company.id), **{key: (value.value if isinstance(value, StrEnum) else value.isoformat() if isinstance(value, date) else value) for key, value in draft.__dict__.items()}, "definition_version": REMITTANCE_VERSION}
        digest = canonical_digest(content)
        existing = await session.scalar(select(PayrollRemittancePolicyRecord).where(PayrollRemittancePolicyRecord.company_id == context.company.id, PayrollRemittancePolicyRecord.policy_digest == digest))
        if existing:
            return existing
        value = PayrollRemittancePolicyRecord(company_id=context.company.id, classification=draft.classification.value, version=draft.version, currency=draft.currency, aggregation_permitted=draft.aggregation_permitted, due_days_after_period=draft.due_days_after_period, destination_required=draft.destination_required, accounting_consequence=draft.accounting_consequence, effective_start=draft.effective_start, effective_end=draft.effective_end, lifecycle="draft", evidence_digest=draft.evidence_digest, policy_digest=digest, created_by_user_id=context.user.id)
        session.add(value); await session.flush(); self._stage(session, context, "remittance_policy", value.id, digest, value.lifecycle, EventType.PAYROLL_REMITTANCE_POLICY_CREATED); await session.commit(); return value

    async def approve_policy(self, session: AsyncSession, *, context: AuthorizationContext, policy_id: UUID) -> PayrollRemittancePolicyRecord:
        self._require(context, PayrollPermission.REMITTANCE_APPROVE)
        value = await session.scalar(select(PayrollRemittancePolicyRecord).where(PayrollRemittancePolicyRecord.company_id == context.company.id, PayrollRemittancePolicyRecord.id == policy_id).with_for_update())
        if value is None or value.lifecycle != "draft" or value.created_by_user_id == context.user.id:
            raise PayrollAuthorizationError("independent draft policy approval is required")
        overlap = await session.scalar(select(PayrollRemittancePolicyRecord.id).where(PayrollRemittancePolicyRecord.company_id == value.company_id, PayrollRemittancePolicyRecord.classification == value.classification, PayrollRemittancePolicyRecord.lifecycle == "approved", PayrollRemittancePolicyRecord.effective_start < (value.effective_end or date.max), func.coalesce(PayrollRemittancePolicyRecord.effective_end, date.max) > value.effective_start))
        if overlap: raise PayrollConflictError("remittance policies overlap")
        value.lifecycle, value.approved_by_user_id, value.approved_at = "approved", context.user.id, datetime.now(timezone.utc); self._stage(session, context, "remittance_policy", value.id, value.policy_digest, value.lifecycle, EventType.PAYROLL_REMITTANCE_POLICY_APPROVED); await session.commit(); return value

    async def create_destination(self, session: AsyncSession, *, context: AuthorizationContext, draft: DraftRemittanceDestination) -> PayrollRemittanceDestinationRecord:
        self._require(context, PayrollPermission.REMITTANCE_MANAGE)
        if not draft.protected_reference.startswith("protected:") or not draft.masked_display or draft.effective_end and draft.effective_end <= draft.effective_start:
            raise PayrollConflictError("protected remittance destination is invalid")
        content = {"company_id": str(context.company.id), "destination_type": draft.destination_type, "jurisdiction_reference": draft.jurisdiction_reference, "protected_reference_digest": canonical_digest({"reference": draft.protected_reference}), "masked_display": draft.masked_display, "effective_start": draft.effective_start.isoformat(), "effective_end": draft.effective_end.isoformat() if draft.effective_end else None}
        digest = canonical_digest(content); identity = f"payroll-remittance-destination:{digest}"
        existing = await session.scalar(select(PayrollRemittanceDestinationRecord).where(PayrollRemittanceDestinationRecord.company_id == context.company.id, PayrollRemittanceDestinationRecord.destination_identity == identity))
        if existing: return existing
        value = PayrollRemittanceDestinationRecord(company_id=context.company.id, destination_type=draft.destination_type, jurisdiction_reference=draft.jurisdiction_reference, protected_reference=draft.protected_reference, masked_display=draft.masked_display, effective_start=draft.effective_start, effective_end=draft.effective_end, lifecycle="draft", destination_identity=identity, destination_digest=digest, created_by_user_id=context.user.id)
        session.add(value); await session.flush(); self._stage(session, context, "remittance_destination", value.id, digest, value.lifecycle, EventType.PAYROLL_REMITTANCE_DESTINATION_CREATED); await session.commit(); return value

    async def approve_destination(self, session: AsyncSession, *, context: AuthorizationContext, destination_id: UUID) -> PayrollRemittanceDestinationRecord:
        self._require(context, PayrollPermission.REMITTANCE_APPROVE)
        value = await session.scalar(select(PayrollRemittanceDestinationRecord).where(PayrollRemittanceDestinationRecord.company_id == context.company.id, PayrollRemittanceDestinationRecord.id == destination_id).with_for_update())
        if value is None or value.lifecycle != "draft" or value.created_by_user_id == context.user.id: raise PayrollAuthorizationError("independent destination approval is required")
        value.lifecycle, value.approved_by_user_id, value.approved_at = "approved", context.user.id, datetime.now(timezone.utc); self._stage(session, context, "remittance_destination", value.id, value.destination_digest, value.lifecycle, EventType.PAYROLL_REMITTANCE_DESTINATION_APPROVED); await session.commit(); return value

    async def identify_obligation(self, session: AsyncSession, *, context: AuthorizationContext, payroll_run_id: UUID, classification: RemittanceClassification, destination_id: UUID | None, supersedes_obligation_id: UUID | None = None) -> PayrollRemittanceObligationRecord:
        self._require(context, PayrollPermission.REMITTANCE_MANAGE)
        run = await session.scalar(select(PayrollRunRecord).where(PayrollRunRecord.company_id == context.company.id, PayrollRunRecord.id == payroll_run_id, PayrollRunRecord.lifecycle == "approved"))
        if run is None: raise PayrollConflictError("approved Payroll run is required")
        period = await session.get(PayPeriod, run.pay_period_id)
        if period is None or period.company_id != context.company.id: raise PayrollConflictError("Payroll period authority is unavailable")
        policy = await self._policy(session, context.company.id, classification, period.period_end)
        destination = None
        if destination_id:
            destination = await session.scalar(select(PayrollRemittanceDestinationRecord).where(PayrollRemittanceDestinationRecord.company_id == context.company.id, PayrollRemittanceDestinationRecord.id == destination_id, PayrollRemittanceDestinationRecord.lifecycle == "approved", PayrollRemittanceDestinationRecord.effective_start <= period.period_end, func.coalesce(PayrollRemittanceDestinationRecord.effective_end, date.max) > period.period_end))
        amount = self._amount(run, classification)
        blocked = policy.destination_required and destination is None or policy.due_days_after_period is None
        members = tuple((await session.scalars(select(PayrollRunMemberRecord).where(PayrollRunMemberRecord.run_id == run.id, PayrollRunMemberRecord.disposition == "ready").order_by(PayrollRunMemberRecord.employee_id))).all())
        contributions = [{"employee_id": str(item.employee_id), "tax_result_id": str(item.tax_result_id), "tax_result_digest": item.tax_result_digest} for item in members]
        due = period.period_end + timedelta(days=policy.due_days_after_period) if policy.due_days_after_period is not None else None
        content = {"company_id": str(run.company_id), "run_id": str(run.id), "run_digest": run.run_digest, "period_id": str(run.pay_period_id), "classification": classification.value, "policy_id": str(policy.id), "policy_digest": policy.policy_digest, "destination_id": str(destination.id) if destination else None, "destination_digest": destination.destination_digest if destination else None, "amount": str(amount), "currency": run.currency, "due_date": due.isoformat() if due else None, "contributions": contributions, "supersedes_obligation_id": str(supersedes_obligation_id) if supersedes_obligation_id else None, "definition_version": REMITTANCE_VERSION}
        digest = canonical_digest(content); identity = f"payroll-remittance-obligation:{digest}"
        await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"remittance:{run.company_id}:{run.id}:{classification.value}"})
        existing = await session.scalar(select(PayrollRemittanceObligationRecord).where(PayrollRemittanceObligationRecord.company_id == run.company_id, PayrollRemittanceObligationRecord.obligation_digest == digest))
        if existing: return existing
        active = await session.scalar(select(PayrollRemittanceObligationRecord.id).where(PayrollRemittanceObligationRecord.company_id == run.company_id, PayrollRemittanceObligationRecord.payroll_run_id == run.id, PayrollRemittanceObligationRecord.classification == classification.value, PayrollRemittanceObligationRecord.lifecycle.not_in(("superseded", "voided", "returned", "reversed"))))
        if active: raise PayrollConflictError("competing remittance obligation exists")
        predecessor = None
        if supersedes_obligation_id:
            predecessor = await session.scalar(select(PayrollRemittanceObligationRecord).where(PayrollRemittanceObligationRecord.company_id == run.company_id, PayrollRemittanceObligationRecord.id == supersedes_obligation_id, PayrollRemittanceObligationRecord.classification == classification.value).with_for_update())
            if predecessor is None or predecessor.lifecycle in {"settled", "partially_settled", "returned", "reversed", "superseded", "voided"} or predecessor.settled_amount:
                raise PayrollConflictError("remittance supersession requires an unconsumed active predecessor")
            predecessor.lifecycle = "superseded"
            await session.flush()
        value = PayrollRemittanceObligationRecord(company_id=run.company_id, payroll_run_id=run.id, pay_period_id=run.pay_period_id, classification=classification.value, source_digest=run.run_digest, contribution_evidence=contributions, policy_id=policy.id, policy_digest=policy.policy_digest, destination_id=destination.id if destination else None, destination_digest=destination.destination_digest if destination else None, obligation_start=period.period_start, obligation_end=period.period_end, due_date=due, amount=amount, settled_amount=Decimal(0), currency=run.currency, lifecycle="blocked" if blocked else "ready_for_review", obligation_identity=identity, obligation_digest=digest, created_by_user_id=context.user.id, supersedes_obligation_id=predecessor.id if predecessor else None)
        session.add(value); await session.flush(); self._stage(session, context, "remittance_obligation", value.id, digest, value.lifecycle, EventType.PAYROLL_REMITTANCE_OBLIGATION_IDENTIFIED); await session.commit(); return value

    async def review(self, session: AsyncSession, *, context: AuthorizationContext, obligation_id: UUID, decision: str, reason_code: str, safe_note: str | None = None) -> PayrollRemittanceReviewRecord:
        self._require(context, PayrollPermission.REMITTANCE_REVIEW)
        value = await self._locked_obligation(session, context, obligation_id)
        if decision not in {"initiated", "accepted", "rejected"}: raise PayrollConflictError("remittance review decision is invalid")
        expected = {"initiated": {"ready_for_review", "rejected"}, "accepted": {"under_review"}, "rejected": {"under_review"}}[decision]
        if value.lifecycle not in expected: raise PayrollConflictError("remittance review lifecycle conflict")
        value.lifecycle = {"initiated": "under_review", "accepted": "ready_for_review", "rejected": "rejected"}[decision]
        record = await self._review_record(session, context, value, decision, reason_code, safe_note); self._stage(session, context, "remittance_obligation", value.id, value.obligation_digest, value.lifecycle, EventType.PAYROLL_REMITTANCE_REVIEWED); await session.commit(); return record

    async def approve(self, session: AsyncSession, *, context: AuthorizationContext, obligation_id: UUID, reason_code: str) -> PayrollRemittanceReviewRecord:
        self._require(context, PayrollPermission.REMITTANCE_APPROVE)
        value = await self._locked_obligation(session, context, obligation_id)
        accepted = await session.scalar(select(PayrollRemittanceReviewRecord.id).where(PayrollRemittanceReviewRecord.obligation_id == value.id, PayrollRemittanceReviewRecord.decision == "accepted"))
        if value.lifecycle != "ready_for_review" or accepted is None: raise PayrollConflictError("review-accepted remittance obligation is required")
        value.lifecycle = "approved_for_remittance"; record = await self._review_record(session, context, value, "approved", reason_code, None); self._stage(session, context, "remittance_obligation", value.id, value.obligation_digest, value.lifecycle, EventType.PAYROLL_REMITTANCE_APPROVED); await session.commit(); return record

    async def prepare_instruction(self, session: AsyncSession, *, context: AuthorizationContext, obligation_id: UUID, provider_identity: str, provider_version: str, idempotency_identity: str) -> PayrollRemittanceInstructionRecord:
        self._require(context, PayrollPermission.REMITTANCE_EXECUTE)
        value = await self._locked_obligation(session, context, obligation_id)
        existing = await session.scalar(select(PayrollRemittanceInstructionRecord).where(PayrollRemittanceInstructionRecord.obligation_id == value.id))
        if existing: return existing
        if value.lifecycle != "approved_for_remittance" or value.destination_id is None: raise PayrollConflictError("approved destination-bound obligation is required")
        content = {"obligation_id": str(value.id), "obligation_digest": value.obligation_digest, "destination_id": str(value.destination_id), "amount": str(value.amount), "currency": value.currency, "provider_identity": provider_identity, "provider_version": provider_version, "idempotency_identity": idempotency_identity}
        digest = canonical_digest(content)
        record = PayrollRemittanceInstructionRecord(company_id=value.company_id, obligation_id=value.id, destination_id=value.destination_id, amount=value.amount, currency=value.currency, provider_identity=provider_identity, provider_version=provider_version, idempotency_identity=idempotency_identity, instruction_identity=f"payroll-remittance-instruction:{digest}", instruction_digest=digest, lifecycle="instruction_prepared", created_by_user_id=context.user.id)
        session.add(record); value.lifecycle = "instruction_prepared"; await session.flush(); self._stage(session, context, "remittance_instruction", record.id, digest, record.lifecycle, EventType.PAYROLL_REMITTANCE_INSTRUCTION_PREPARED); await session.commit(); return record

    async def submit(self, session: AsyncSession, *, context: AuthorizationContext, instruction_id: UUID, provider: RemittanceProvider) -> PayrollRemittanceInstructionRecord:
        self._require(context, PayrollPermission.REMITTANCE_EXECUTE)
        instruction = await self._locked_instruction(session, context, instruction_id)
        if instruction.lifecycle in {"provider_acknowledged", "submitted", "settlement_pending", "partially_settled", "settled", "rejected"}: return instruction
        if instruction.lifecycle == "uncertain": raise PayrollConflictError("uncertain remittance requires reconciliation before retry")
        if provider.identity != instruction.provider_identity or provider.version != instruction.provider_version: raise PayrollConflictError("remittance provider identity mismatch")
        destination = await session.scalar(select(PayrollRemittanceDestinationRecord).where(PayrollRemittanceDestinationRecord.company_id == context.company.id, PayrollRemittanceDestinationRecord.id == instruction.destination_id, PayrollRemittanceDestinationRecord.lifecycle == "approved"))
        if destination is None: raise PayrollConflictError("approved remittance destination is unavailable")
        request_digest = canonical_digest({"instruction_digest": instruction.instruction_digest, "protected_destination_digest": canonical_digest({"reference": destination.protected_reference}), "amount": str(instruction.amount), "currency": instruction.currency})
        instruction.lifecycle = "submission_pending"; await session.flush()
        acknowledgement = await provider.submit(RemittanceProviderRequest(instruction.instruction_identity, instruction.instruction_digest, destination.protected_reference, instruction.amount, instruction.currency, instruction.idempotency_identity, request_digest))
        return await self.record_acknowledgement(session, context=context, instruction_id=instruction.id, acknowledgement=acknowledgement)

    async def record_acknowledgement(self, session: AsyncSession, *, context: AuthorizationContext, instruction_id: UUID, acknowledgement: RemittanceAcknowledgement) -> PayrollRemittanceInstructionRecord:
        self._require(context, PayrollPermission.REMITTANCE_EXECUTE)
        instruction = await self._locked_instruction(session, context, instruction_id)
        existing = await session.scalar(select(PayrollRemittanceEvidenceRecord).where(PayrollRemittanceEvidenceRecord.instruction_id == instruction.id, PayrollRemittanceEvidenceRecord.evidence_digest == acknowledgement.response_digest))
        if existing: return instruction
        if instruction.request_digest and instruction.request_digest != acknowledgement.request_digest or instruction.response_digest and instruction.response_digest != acknowledgement.response_digest: raise PayrollConflictError("contradictory remittance acknowledgement")
        state = {ProviderState.ACKNOWLEDGED: "provider_acknowledged", ProviderState.PENDING: "submitted", ProviderState.REJECTED: "rejected", ProviderState.UNCERTAIN: "uncertain"}[acknowledgement.state]
        instruction.lifecycle, instruction.request_digest, instruction.response_digest, instruction.provider_reference = state, acknowledgement.request_digest, acknowledgement.response_digest, acknowledgement.provider_safe_reference
        obligation = await self._locked_obligation(session, context, instruction.obligation_id); obligation.lifecycle = state
        session.add(PayrollRemittanceEvidenceRecord(company_id=instruction.company_id, instruction_id=instruction.id, evidence_type="acknowledgement", amount=None, provider_safe_reference=acknowledgement.provider_safe_reference, evidence_digest=acknowledgement.response_digest, occurred_at=acknowledgement.acknowledged_at, recorded_by_user_id=context.user.id)); self._stage(session, context, "remittance_instruction", instruction.id, instruction.instruction_digest, state, EventType.PAYROLL_REMITTANCE_ACKNOWLEDGED); await session.commit(); return instruction

    async def record_settlement(self, session: AsyncSession, *, context: AuthorizationContext, instruction_id: UUID, amount: Decimal, provider_safe_reference: str, occurred_at: datetime) -> PayrollRemittanceInstructionRecord:
        self._require(context, PayrollPermission.REMITTANCE_RECONCILE)
        instruction = await self._locked_instruction(session, context, instruction_id); obligation = await self._locked_obligation(session, context, instruction.obligation_id)
        if instruction.lifecycle not in {"provider_acknowledged", "settlement_pending", "partially_settled"} or amount <= 0 or obligation.settled_amount + amount > obligation.amount: raise PayrollConflictError("remittance settlement evidence is invalid")
        digest = canonical_digest({"instruction_id": str(instruction.id), "amount": str(amount), "reference": provider_safe_reference, "occurred_at": occurred_at.isoformat()})
        existing = await session.scalar(select(PayrollRemittanceEvidenceRecord).where(PayrollRemittanceEvidenceRecord.instruction_id == instruction.id, PayrollRemittanceEvidenceRecord.evidence_digest == digest))
        if existing: return instruction
        obligation.settled_amount += amount
        state = "settled" if obligation.settled_amount == obligation.amount else "partially_settled"
        obligation.lifecycle = instruction.lifecycle = state
        session.add(PayrollRemittanceEvidenceRecord(company_id=instruction.company_id, instruction_id=instruction.id, evidence_type="settlement", amount=amount, provider_safe_reference=provider_safe_reference, evidence_digest=digest, occurred_at=occurred_at, recorded_by_user_id=context.user.id)); self._stage(session, context, "remittance_instruction", instruction.id, instruction.instruction_digest, state, EventType.PAYROLL_REMITTANCE_SETTLED); await session.commit(); return instruction

    async def record_return(self, session: AsyncSession, *, context: AuthorizationContext, instruction_id: UUID, amount: Decimal, provider_safe_reference: str, occurred_at: datetime) -> PayrollRemittanceEvidenceRecord:
        self._require(context, PayrollPermission.REMITTANCE_RECONCILE)
        instruction = await self._locked_instruction(session, context, instruction_id); obligation = await self._locked_obligation(session, context, instruction.obligation_id)
        if amount <= 0 or amount > obligation.settled_amount: raise PayrollConflictError("remittance return evidence is invalid")
        digest = canonical_digest({"instruction_id": str(instruction.id), "return_amount": str(amount), "reference": provider_safe_reference, "occurred_at": occurred_at.isoformat()})
        existing = await session.scalar(select(PayrollRemittanceEvidenceRecord).where(PayrollRemittanceEvidenceRecord.instruction_id == instruction.id, PayrollRemittanceEvidenceRecord.evidence_digest == digest))
        if existing: return existing
        obligation.settled_amount -= amount; obligation.lifecycle = instruction.lifecycle = "returned"
        record = PayrollRemittanceEvidenceRecord(company_id=instruction.company_id, instruction_id=instruction.id, evidence_type="return", amount=amount, provider_safe_reference=provider_safe_reference, evidence_digest=digest, occurred_at=occurred_at, recorded_by_user_id=context.user.id); session.add(record); self._stage(session, context, "remittance_instruction", instruction.id, instruction.instruction_digest, "returned", EventType.PAYROLL_REMITTANCE_RETURNED); await session.commit(); return record

    async def schedule_state(self, session: AsyncSession, *, context: AuthorizationContext, obligation_id: UUID, as_of: date) -> ScheduleState:
        self._require(context, PayrollPermission.REMITTANCE_READ); value = await self._locked_obligation(session, context, obligation_id)
        if value.lifecycle == "blocked" or value.due_date is None: return ScheduleState.BLOCKED
        if value.lifecycle == "settled": return ScheduleState.NOT_APPLICABLE
        if as_of < value.due_date: return ScheduleState.NOT_DUE
        return ScheduleState.DUE if as_of == value.due_date else ScheduleState.OVERDUE

    async def reconcile(self, session: AsyncSession, *, context: AuthorizationContext, obligation_id: UUID) -> RemittanceReconciliation:
        self._require(context, PayrollPermission.REMITTANCE_READ); value = await self._locked_obligation(session, context, obligation_id)
        instruction = await session.scalar(select(PayrollRemittanceInstructionRecord).where(PayrollRemittanceInstructionRecord.obligation_id == value.id))
        instruction_total = instruction.amount if instruction else Decimal(0); outstanding = value.amount - value.settled_amount
        if instruction and instruction_total != value.amount: raise PayrollConflictError("remittance instruction reconciliation failed")
        digest = canonical_digest({"obligation_id": str(value.id), "source_total": str(value.amount), "instruction_total": str(instruction_total), "settled": str(value.settled_amount), "outstanding": str(outstanding), "lifecycle": value.lifecycle})
        return RemittanceReconciliation(value.amount, value.amount, instruction_total, value.settled_amount, outstanding, value.lifecycle, digest)

    async def accounting_handoff(self, session: AsyncSession, *, context: AuthorizationContext, obligation_id: UUID) -> RemittanceAccountingHandoff:
        self._require(context, PayrollPermission.REMITTANCE_READ); value = await self._locked_obligation(session, context, obligation_id)
        instruction = await session.scalar(select(PayrollRemittanceInstructionRecord).where(PayrollRemittanceInstructionRecord.obligation_id == value.id))
        if instruction is None or value.settled_amount <= 0: raise PayrollConflictError("proven remittance settlement is required")
        evidence = tuple((await session.scalars(select(PayrollRemittanceEvidenceRecord.evidence_digest).where(PayrollRemittanceEvidenceRecord.instruction_id == instruction.id, PayrollRemittanceEvidenceRecord.evidence_type == "settlement").order_by(PayrollRemittanceEvidenceRecord.occurred_at))).all())
        event = "tax_remittance" if value.classification in {RemittanceClassification.EMPLOYEE_TAX_WITHHOLDING.value, RemittanceClassification.EMPLOYER_PAYROLL_TAX.value} else "deduction_remittance"
        return RemittanceAccountingHandoff(value.id, value.obligation_digest, instruction.id, evidence, value.settled_amount, value.currency, event)

    async def obligations(self, session: AsyncSession, *, context: AuthorizationContext) -> tuple[PayrollRemittanceObligationRecord, ...]:
        self._require(context, PayrollPermission.REMITTANCE_READ); return tuple((await session.scalars(select(PayrollRemittanceObligationRecord).where(PayrollRemittanceObligationRecord.company_id == context.company.id).order_by(PayrollRemittanceObligationRecord.created_at))).all())

    async def _policy(self, session: AsyncSession, company_id: UUID, classification: RemittanceClassification, effective: date) -> PayrollRemittancePolicyRecord:
        values = tuple((await session.scalars(select(PayrollRemittancePolicyRecord).where(PayrollRemittancePolicyRecord.company_id == company_id, PayrollRemittancePolicyRecord.classification == classification.value, PayrollRemittancePolicyRecord.lifecycle == "approved", PayrollRemittancePolicyRecord.effective_start <= effective, func.coalesce(PayrollRemittancePolicyRecord.effective_end, date.max) > effective))).all())
        if len(values) != 1: raise PayrollConflictError("exactly one approved effective remittance policy is required")
        return values[0]

    @staticmethod
    def _amount(run: PayrollRunRecord, classification: RemittanceClassification) -> Decimal:
        mapping = {RemittanceClassification.EMPLOYEE_TAX_WITHHOLDING: run.aggregate_employee_taxes, RemittanceClassification.EMPLOYER_PAYROLL_TAX: run.aggregate_employer_contributions, RemittanceClassification.EMPLOYEE_DEDUCTION: run.aggregate_employee_deductions, RemittanceClassification.EMPLOYER_BENEFIT_CONTRIBUTION: run.aggregate_employer_contributions}
        if classification not in mapping or mapping[classification] <= 0: raise PayrollConflictError("Payroll run contains no authoritative liability for classification")
        return mapping[classification]

    async def _review_record(self, session: AsyncSession, context: AuthorizationContext, value: PayrollRemittanceObligationRecord, decision: str, reason: str, note: str | None) -> PayrollRemittanceReviewRecord:
        reason, note = reason.strip(), note.strip() if note else None
        if not reason or len(reason) > 80 or note and (len(note) > 500 or "$" in note): raise PayrollConflictError("unsafe remittance review evidence")
        replay = await session.scalar(select(PayrollRemittanceReviewRecord).where(PayrollRemittanceReviewRecord.obligation_id == value.id, PayrollRemittanceReviewRecord.actor_user_id == context.user.id, PayrollRemittanceReviewRecord.decision == decision, PayrollRemittanceReviewRecord.reason_code == reason, PayrollRemittanceReviewRecord.safe_note == note))
        if replay: return replay
        sequence = (await session.scalar(select(func.count(PayrollRemittanceReviewRecord.id)).where(PayrollRemittanceReviewRecord.obligation_id == value.id)) or 0) + 1; at = datetime.now(timezone.utc); digest = canonical_digest({"obligation_id": str(value.id), "digest": value.obligation_digest, "sequence": sequence, "actor": str(context.user.id), "decision": decision, "reason": reason, "note": note, "at": at.isoformat()})
        record = PayrollRemittanceReviewRecord(company_id=value.company_id, obligation_id=value.id, sequence=sequence, actor_user_id=context.user.id, decision=decision, reason_code=reason, safe_note=note, obligation_digest=value.obligation_digest, review_digest=digest, reviewed_at=at); session.add(record); await session.flush(); return record

    async def _locked_obligation(self, session: AsyncSession, context: AuthorizationContext, obligation_id: UUID) -> PayrollRemittanceObligationRecord:
        value = await session.scalar(select(PayrollRemittanceObligationRecord).where(PayrollRemittanceObligationRecord.company_id == context.company.id, PayrollRemittanceObligationRecord.id == obligation_id).with_for_update())
        if value is None: raise PayrollConflictError("remittance obligation was not found")
        return value

    async def _locked_instruction(self, session: AsyncSession, context: AuthorizationContext, instruction_id: UUID) -> PayrollRemittanceInstructionRecord:
        value = await session.scalar(select(PayrollRemittanceInstructionRecord).where(PayrollRemittanceInstructionRecord.company_id == context.company.id, PayrollRemittanceInstructionRecord.id == instruction_id).with_for_update())
        if value is None: raise PayrollConflictError("remittance instruction was not found")
        return value

    @staticmethod
    def _require(context: AuthorizationContext, permission: str) -> None:
        if not context.has_permission(permission): raise PayrollAuthorizationError("Payroll remittance permission denied")

    def _stage(self, session: AsyncSession, context: AuthorizationContext, entity: str, entity_id: UUID, digest: str, lifecycle: str, event: EventType) -> None:
        details: dict[str, object] = {"entity_id": str(entity_id), "evidence_digest": digest, "lifecycle": lifecycle}
        BusinessEventService.stage(session, BusinessEventCreate(event_type=event, entity_type=f"payroll_{entity}", entity_id=entity_id, company_id=context.company.id, user_id=context.user.id, payload=details)); self._audit.stage(session, AuditEntry(action=event.value, resource_type=f"payroll_{entity}", actor_user_id=context.user.id, company_id=context.company.id, resource_id=entity_id, details=details))
