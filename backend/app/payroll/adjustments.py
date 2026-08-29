"""Append-only Payroll correction authority; never mutates historical evidence."""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.models import Journal
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, AuditService, audit_service
from app.platform.permissions.authorization import AuthorizationContext

from .accounting_posting import PayrollPostingFactCandidate
from .contracts import PayrollAuthorizationError, PayrollConflictError, canonical_digest
from .models import (
    PayrollAdjustmentAuthorityRecord,
    PayrollAdjustmentReviewRecord,
    PayrollGrossCalculationResultRecord,
    PayrollPaymentExecutionEvidenceRecord,
    PayrollPaymentExecutionRecord,
    PayrollPaymentReleaseRecord,
    PayrollRunRecord,
    PayrollTaxDeductionResultRecord,
)
from .permissions import PayrollPermission

ADJUSTMENT_VERSION = "payroll.adjustment-authority.v1"


class PayrollCorrectionType(StrEnum):
    PRE_PAYMENT_PAYROLL_CORRECTION = "pre_payment_payroll_correction"
    RETROACTIVE_EARNINGS = "retroactive_earnings"
    OFF_CYCLE_PAYROLL = "off_cycle_payroll"
    TAX_CORRECTION = "tax_correction"
    DEDUCTION_CORRECTION = "deduction_correction"
    PAYMENT_RETURN = "payment_return"
    PAYMENT_REJECTION = "payment_rejection"
    PAYMENT_REVERSAL = "payment_reversal"
    SETTLEMENT_CORRECTION = "settlement_correction"
    ACCOUNTING_ADJUSTMENT_REQUIRED = "accounting_adjustment_required"


class AdjustmentReviewDecision(StrEnum):
    INITIATED = "initiated"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    APPROVED = "approved"


@dataclass(frozen=True)
class EconomicDelta:
    component: str
    amount: Decimal


@dataclass(frozen=True)
class DraftPayrollAdjustment:
    classification: PayrollCorrectionType
    reason_code: str
    source_type: str
    source_id: UUID
    source_digest: str
    currency: str
    effective_date: date
    evidence_digest: str
    delta_components: tuple[EconomicDelta, ...]
    employee_id: UUID | None = None
    original_pay_period_id: UUID | None = None
    off_cycle_pay_period_id: UUID | None = None
    supersedes_adjustment_id: UUID | None = None
    safe_note: str | None = None


@dataclass(frozen=True)
class AdjustmentConsequence:
    adjustment_id: UUID
    adjustment_digest: str
    classification: PayrollCorrectionType
    requires_successor_payroll: bool
    requires_payment_recovery: bool
    requires_accounting_adjustment: bool
    original_evidence_immutable: bool = True


class PayrollAdjustmentService:
    def __init__(self, *, audit: AuditService = audit_service) -> None:
        self._audit = audit

    async def create(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        draft: DraftPayrollAdjustment,
        posting_candidate: PayrollPostingFactCandidate | None = None,
    ) -> PayrollAdjustmentAuthorityRecord:
        self._require(context, PayrollPermission.ADJUSTMENT_MANAGE)
        self._validate_draft(draft)
        source_evidence = await self._verify_source(session, context, draft, posting_candidate)
        canonical = {
            "company_id": str(context.company.id),
            "classification": draft.classification.value,
            "reason_code": draft.reason_code,
            "source_type": draft.source_type,
            "source_id": str(draft.source_id),
            "source_digest": draft.source_digest,
            "currency": draft.currency,
            "effective_date": draft.effective_date.isoformat(),
            "evidence_digest": draft.evidence_digest,
            "deltas": tuple((item.component, str(item.amount)) for item in sorted(draft.delta_components, key=lambda item: item.component)),
            "employee_id": str(draft.employee_id) if draft.employee_id else None,
            "original_pay_period_id": str(draft.original_pay_period_id) if draft.original_pay_period_id else None,
            "off_cycle_pay_period_id": str(draft.off_cycle_pay_period_id) if draft.off_cycle_pay_period_id else None,
            "supersedes_adjustment_id": str(draft.supersedes_adjustment_id) if draft.supersedes_adjustment_id else None,
            "definition_version": ADJUSTMENT_VERSION,
        }
        digest = canonical_digest(canonical)
        await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"payroll-adjustment:{context.company.id}:{draft.source_type}:{draft.source_id}:{draft.classification.value}"})
        existing = await session.scalar(select(PayrollAdjustmentAuthorityRecord).where(PayrollAdjustmentAuthorityRecord.company_id == context.company.id, PayrollAdjustmentAuthorityRecord.adjustment_digest == digest))
        if existing:
            return existing
        active = await session.scalar(select(PayrollAdjustmentAuthorityRecord).where(PayrollAdjustmentAuthorityRecord.company_id == context.company.id, PayrollAdjustmentAuthorityRecord.source_type == draft.source_type, PayrollAdjustmentAuthorityRecord.source_id == draft.source_id, PayrollAdjustmentAuthorityRecord.classification == draft.classification.value, PayrollAdjustmentAuthorityRecord.lifecycle.in_(("draft", "under_review", "approved"))).with_for_update())
        predecessor = None
        if draft.supersedes_adjustment_id:
            predecessor = await session.scalar(select(PayrollAdjustmentAuthorityRecord).where(PayrollAdjustmentAuthorityRecord.company_id == context.company.id, PayrollAdjustmentAuthorityRecord.id == draft.supersedes_adjustment_id).with_for_update())
            if predecessor is None or active is None or predecessor.id != active.id or predecessor.lifecycle == "applied_to_successor_authority":
                raise PayrollConflictError("Payroll adjustment supersession lineage conflicts")
            predecessor.lifecycle = "superseded"
        elif active:
            raise PayrollConflictError("competing active Payroll adjustment exists")
        value = PayrollAdjustmentAuthorityRecord(company_id=context.company.id, employee_id=draft.employee_id, original_pay_period_id=draft.original_pay_period_id, off_cycle_pay_period_id=draft.off_cycle_pay_period_id, classification=draft.classification.value, reason_code=draft.reason_code, source_type=draft.source_type, source_id=draft.source_id, source_digest=draft.source_digest, source_evidence=source_evidence, delta_components=[{"component": item.component, "amount": str(item.amount)} for item in sorted(draft.delta_components, key=lambda item: item.component)], currency=draft.currency, effective_date=draft.effective_date, evidence_digest=draft.evidence_digest, definition_version=ADJUSTMENT_VERSION, adjustment_identity=f"payroll-adjustment:{digest}", adjustment_digest=digest, lifecycle="draft", created_by_user_id=context.user.id, supersedes_adjustment_id=predecessor.id if predecessor else None)
        session.add(value)
        await session.flush()
        if predecessor:
            self._stage(session, context, predecessor, EventType.PAYROLL_ADJUSTMENT_SUPERSEDED, "payroll.adjustment.superseded")
        self._stage(session, context, value, EventType.PAYROLL_ADJUSTMENT_CREATED, "payroll.adjustment.created")
        await session.commit()
        return value

    async def initiate_review(self, session: AsyncSession, *, context: AuthorizationContext, adjustment_id: UUID, reason_code: str) -> PayrollAdjustmentReviewRecord:
        self._require(context, PayrollPermission.ADJUSTMENT_REVIEW)
        value = await self._locked(session, context, adjustment_id)
        if value.lifecycle not in {"draft", "rejected"}:
            raise PayrollConflictError("Payroll adjustment cannot enter review")
        value.lifecycle = "under_review"
        record = await self._review(session, context, value, AdjustmentReviewDecision.INITIATED, reason_code)
        self._stage(session, context, value, EventType.PAYROLL_ADJUSTMENT_REVIEWED, "payroll.adjustment.review_initiated")
        await session.commit()
        return record

    async def decide_review(self, session: AsyncSession, *, context: AuthorizationContext, adjustment_id: UUID, decision: AdjustmentReviewDecision, reason_code: str) -> PayrollAdjustmentReviewRecord:
        self._require(context, PayrollPermission.ADJUSTMENT_REVIEW)
        if decision not in {AdjustmentReviewDecision.ACCEPTED, AdjustmentReviewDecision.REJECTED}:
            raise PayrollConflictError("Payroll adjustment review decision is invalid")
        value = await self._locked(session, context, adjustment_id)
        if value.lifecycle != "under_review":
            raise PayrollConflictError("Payroll adjustment is not under review")
        value.lifecycle = "draft" if decision is AdjustmentReviewDecision.ACCEPTED else "rejected"
        record = await self._review(session, context, value, decision, reason_code)
        self._stage(session, context, value, EventType.PAYROLL_ADJUSTMENT_REVIEWED, f"payroll.adjustment.review_{decision.value}")
        await session.commit()
        return record

    async def approve(self, session: AsyncSession, *, context: AuthorizationContext, adjustment_id: UUID, reason_code: str) -> PayrollAdjustmentReviewRecord:
        self._require(context, PayrollPermission.ADJUSTMENT_APPROVE)
        value = await self._locked(session, context, adjustment_id)
        accepted = await session.scalar(select(PayrollAdjustmentReviewRecord.id).where(PayrollAdjustmentReviewRecord.adjustment_id == value.id, PayrollAdjustmentReviewRecord.decision == "accepted"))
        if value.lifecycle != "draft" or accepted is None:
            raise PayrollConflictError("review-accepted Payroll adjustment is required")
        value.lifecycle, value.approved_by_user_id, value.approved_at = "approved", context.user.id, datetime.now(timezone.utc)
        record = await self._review(session, context, value, AdjustmentReviewDecision.APPROVED, reason_code)
        self._stage(session, context, value, EventType.PAYROLL_ADJUSTMENT_APPROVED, "payroll.adjustment.approved")
        await session.commit()
        return record

    async def consequence(self, session: AsyncSession, *, context: AuthorizationContext, adjustment_id: UUID) -> AdjustmentConsequence:
        self._require(context, PayrollPermission.ADJUSTMENT_READ)
        value = await session.scalar(select(PayrollAdjustmentAuthorityRecord).where(PayrollAdjustmentAuthorityRecord.company_id == context.company.id, PayrollAdjustmentAuthorityRecord.id == adjustment_id, PayrollAdjustmentAuthorityRecord.lifecycle == "approved"))
        if value is None:
            raise PayrollConflictError("approved Payroll adjustment is unavailable")
        classification = PayrollCorrectionType(value.classification)
        return AdjustmentConsequence(value.id, value.adjustment_digest, classification, classification in {PayrollCorrectionType.PRE_PAYMENT_PAYROLL_CORRECTION, PayrollCorrectionType.RETROACTIVE_EARNINGS, PayrollCorrectionType.OFF_CYCLE_PAYROLL, PayrollCorrectionType.TAX_CORRECTION, PayrollCorrectionType.DEDUCTION_CORRECTION}, classification in {PayrollCorrectionType.PAYMENT_RETURN, PayrollCorrectionType.PAYMENT_REJECTION, PayrollCorrectionType.PAYMENT_REVERSAL, PayrollCorrectionType.SETTLEMENT_CORRECTION}, classification in {PayrollCorrectionType.ACCOUNTING_ADJUSTMENT_REQUIRED, PayrollCorrectionType.PAYMENT_RETURN, PayrollCorrectionType.PAYMENT_REVERSAL, PayrollCorrectionType.SETTLEMENT_CORRECTION})

    async def _verify_source(self, session: AsyncSession, context: AuthorizationContext, draft: DraftPayrollAdjustment, candidate: PayrollPostingFactCandidate | None) -> dict[str, object]:
        model_and_digest = {
            "gross_result": (PayrollGrossCalculationResultRecord, "calculation_digest"),
            "tax_result": (PayrollTaxDeductionResultRecord, "calculation_digest"),
            "payroll_run": (PayrollRunRecord, "run_digest"),
            "payment_release": (PayrollPaymentReleaseRecord, "package_digest"),
            "payment_execution": (PayrollPaymentExecutionRecord, "execution_digest"),
            "settlement_evidence": (PayrollPaymentExecutionEvidenceRecord, "evidence_digest"),
        }
        if draft.source_type == "payroll_posting_fact_candidate":
            if candidate is None:
                raise PayrollConflictError("verified Payroll PostingFact candidate is required")
            candidate.verify()
            if candidate.fact.company_id != context.company.id or candidate.fact.source_event_id != draft.source_id or candidate.candidate_identity.rsplit(":", 1)[-1] != draft.source_digest:
                raise PayrollConflictError("Payroll PostingFact candidate source mismatch")
            return {"posting_fact_identity": candidate.candidate_identity, "posting_fact_digest": candidate.fact.canonical_digest(), "posted": False}
        if draft.source_type == "posted_accounting_journal":
            value = await session.scalar(select(Journal).where(Journal.company_id == context.company.id, Journal.id == draft.source_id, Journal.status == "posted", Journal.source_digest == draft.source_digest))
            if value is None:
                raise PayrollConflictError("posted Accounting source authority is unavailable")
            return {"journal_id": str(value.id), "journal_source_digest": value.source_digest, "posted": True}
        definition = model_and_digest.get(draft.source_type)
        if definition is None:
            raise PayrollConflictError("Payroll adjustment source type is unsupported")
        raw_model, digest_field = definition
        model: Any = raw_model
        value = await session.scalar(select(model).where(model.company_id == context.company.id, model.id == draft.source_id, getattr(model, digest_field) == draft.source_digest))
        if value is None:
            raise PayrollConflictError("authoritative Payroll adjustment source is unavailable")
        return {"source_id": str(draft.source_id), "source_digest": draft.source_digest, "source_type": draft.source_type}

    @staticmethod
    def _validate_draft(draft: DraftPayrollAdjustment) -> None:
        if not draft.reason_code.strip() or len(draft.reason_code) > 80 or len(draft.source_digest) != 64 or len(draft.evidence_digest) != 64:
            raise PayrollConflictError("Payroll adjustment evidence is invalid")
        if not draft.delta_components or len({item.component for item in draft.delta_components}) != len(draft.delta_components):
            raise PayrollConflictError("Payroll adjustment delta is incomplete")
        if any(not item.component.strip() or not item.amount.is_finite() or item.amount == 0 for item in draft.delta_components):
            raise PayrollConflictError("Payroll adjustment delta is invalid")
        if draft.classification is PayrollCorrectionType.OFF_CYCLE_PAYROLL and (draft.original_pay_period_id is None or draft.off_cycle_pay_period_id is None or draft.original_pay_period_id == draft.off_cycle_pay_period_id):
            raise PayrollConflictError("off-cycle Payroll requires distinct period authority")

    async def _review(self, session: AsyncSession, context: AuthorizationContext, value: PayrollAdjustmentAuthorityRecord, decision: AdjustmentReviewDecision, reason_code: str) -> PayrollAdjustmentReviewRecord:
        reason = reason_code.strip()
        if not reason or len(reason) > 80:
            raise PayrollConflictError("Payroll adjustment review reason is invalid")
        sequence = (await session.scalar(select(func.count(PayrollAdjustmentReviewRecord.id)).where(PayrollAdjustmentReviewRecord.adjustment_id == value.id)) or 0) + 1
        at = datetime.now(timezone.utc)
        digest = canonical_digest({"adjustment_id": str(value.id), "adjustment_digest": value.adjustment_digest, "sequence": sequence, "actor": str(context.user.id), "decision": decision.value, "reason": reason, "at": at.isoformat()})
        record = PayrollAdjustmentReviewRecord(company_id=value.company_id, adjustment_id=value.id, sequence=sequence, actor_user_id=context.user.id, decision=decision.value, reason_code=reason, safe_note=None, adjustment_digest=value.adjustment_digest, review_digest=digest, reviewed_at=at)
        session.add(record)
        await session.flush()
        return record

    @staticmethod
    async def _locked(session: AsyncSession, context: AuthorizationContext, adjustment_id: UUID) -> PayrollAdjustmentAuthorityRecord:
        value = await session.scalar(select(PayrollAdjustmentAuthorityRecord).where(PayrollAdjustmentAuthorityRecord.company_id == context.company.id, PayrollAdjustmentAuthorityRecord.id == adjustment_id).with_for_update())
        if value is None:
            raise PayrollConflictError("Payroll adjustment was not found")
        return value

    @staticmethod
    def _require(context: AuthorizationContext, permission: str) -> None:
        if not context.has_permission(permission):
            raise PayrollAuthorizationError("Payroll adjustment permission denied")

    def _stage(self, session: AsyncSession, context: AuthorizationContext, value: PayrollAdjustmentAuthorityRecord, event: EventType, action: str) -> None:
        details: dict[str, object] = {"adjustment_id": str(value.id), "adjustment_digest": value.adjustment_digest, "classification": value.classification, "source_type": value.source_type, "source_id": str(value.source_id), "lifecycle": value.lifecycle}
        BusinessEventService.stage(session, BusinessEventCreate(event_type=event, entity_type="payroll_adjustment", entity_id=value.id, company_id=value.company_id, user_id=context.user.id, payload=details))
        self._audit.stage(session, AuditEntry(action=action, resource_type="payroll_adjustment", actor_user_id=context.user.id, company_id=value.company_id, resource_id=value.id, details=details))
