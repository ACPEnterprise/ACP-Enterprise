"""Immutable persistence, review, and successor handoff for Payroll adjustments."""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, AuditService, audit_service
from app.platform.permissions.authorization import AuthorizationContext

from .adjustment_calculation import (
    CalculatedAdjustmentComponent,
    PayrollAdjustmentCalculationCandidate,
    RecognitionEffect,
)
from .adjustments import PayrollCorrectionType
from .contracts import PayrollAuthorizationError, PayrollConflictError, canonical_digest
from .models import (
    PayrollAdjustmentApplicationRecord,
    PayrollAdjustmentAuthorityRecord,
    PayrollAdjustmentResultRecord,
    PayrollAdjustmentResultReviewRecord,
)
from .permissions import PayrollPermission


class AdjustmentResultDecision(StrEnum):
    INITIATED = "initiated"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    APPROVED = "approved"


@dataclass(frozen=True)
class SuccessorApplication:
    result_id: UUID
    result_digest: str
    purpose: str
    successor_authority_type: str
    component_deltas: tuple[dict[str, object], ...]
    application_digest: str


class PayrollAdjustmentResultService:
    def __init__(self, *, audit: AuditService = audit_service) -> None:
        self._audit = audit

    async def persist_candidate(self, session: AsyncSession, *, context: AuthorizationContext, candidate: PayrollAdjustmentCalculationCandidate, supersedes_result_id: UUID | None = None) -> PayrollAdjustmentResultRecord:
        self._require(context, PayrollPermission.ADJUSTMENT_CALCULATE)
        candidate.verify()
        authority = await session.scalar(select(PayrollAdjustmentAuthorityRecord).where(PayrollAdjustmentAuthorityRecord.company_id == context.company.id, PayrollAdjustmentAuthorityRecord.id == candidate.adjustment_id, PayrollAdjustmentAuthorityRecord.adjustment_digest == candidate.adjustment_digest, PayrollAdjustmentAuthorityRecord.lifecycle == "approved"))
        if authority is None:
            raise PayrollConflictError("approved adjustment authority is required")
        if (candidate.company_id != context.company.id or candidate.employee_id != authority.employee_id or candidate.original_pay_period_id != authority.original_pay_period_id or candidate.correction_pay_period_id != authority.off_cycle_pay_period_id or candidate.source_id != authority.source_id or candidate.source_digest != authority.source_digest or candidate.source_type != authority.source_type or candidate.currency != authority.currency or candidate.classification.value != authority.classification):
            raise PayrollConflictError("adjustment result admission scope mismatch")
        await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"payroll-adjustment-result:{context.company.id}:{candidate.adjustment_id}"})
        existing = await session.scalar(select(PayrollAdjustmentResultRecord).where(PayrollAdjustmentResultRecord.company_id == context.company.id, PayrollAdjustmentResultRecord.calculation_digest == candidate.calculation_digest))
        if existing:
            self._verify(existing, await self._predecessor_identity(session, existing))
            if existing.result_identity != candidate.result_identity:
                raise PayrollConflictError("adjustment result identity conflict")
            return existing
        active = await session.scalar(select(PayrollAdjustmentResultRecord).where(PayrollAdjustmentResultRecord.company_id == context.company.id, PayrollAdjustmentResultRecord.adjustment_id == candidate.adjustment_id, PayrollAdjustmentResultRecord.lifecycle.in_(("calculated", "under_review", "approved"))).with_for_update())
        predecessor = None
        if supersedes_result_id:
            predecessor = await session.scalar(select(PayrollAdjustmentResultRecord).where(PayrollAdjustmentResultRecord.company_id == context.company.id, PayrollAdjustmentResultRecord.id == supersedes_result_id).with_for_update())
            if predecessor is None or active is None or predecessor.id != active.id or predecessor.lifecycle == "applied_to_successor_authority":
                raise PayrollConflictError("adjustment result supersession lineage conflict")
            predecessor.lifecycle = "superseded"
        elif active:
            raise PayrollConflictError("active adjustment result already exists")
        value = PayrollAdjustmentResultRecord(company_id=candidate.company_id, employee_id=candidate.employee_id, original_pay_period_id=candidate.original_pay_period_id, correction_pay_period_id=candidate.correction_pay_period_id, adjustment_id=candidate.adjustment_id, adjustment_digest=candidate.adjustment_digest, source_type=candidate.source_type, source_id=candidate.source_id, source_digest=candidate.source_digest, classification=candidate.classification.value, currency=candidate.currency, components=[item.canonical_content() for item in candidate.components], consequences=[item.value for item in candidate.consequences], result_identity=candidate.result_identity, calculation_version=candidate.definition_version, calculation_digest=candidate.calculation_digest, calculated_at=candidate.calculated_at, created_by_user_id=context.user.id, lifecycle="calculated", supersedes_result_id=predecessor.id if predecessor else None)
        session.add(value)
        await session.flush()
        self._verify(value, predecessor.result_identity if predecessor else None)
        if predecessor:
            self._stage(session, context, predecessor, EventType.PAYROLL_ADJUSTMENT_RESULT_SUPERSEDED, "payroll.adjustment_result.superseded")
        self._stage(session, context, value, EventType.PAYROLL_ADJUSTMENT_RESULT_PERSISTED, "payroll.adjustment_result.persisted")
        await session.commit()
        return value

    async def initiate_review(self, session: AsyncSession, *, context: AuthorizationContext, result_id: UUID, reason_code: str, safe_note: str | None = None) -> PayrollAdjustmentResultReviewRecord:
        self._require(context, PayrollPermission.ADJUSTMENT_RESULT_REVIEW)
        value = await self._locked(session, context, result_id)
        if value.lifecycle not in {"calculated", "rejected"}:
            raise PayrollConflictError("adjustment result cannot enter review")
        value.lifecycle = "under_review"
        record = await self._review(session, context, value, AdjustmentResultDecision.INITIATED, reason_code, safe_note)
        self._stage(session, context, value, EventType.PAYROLL_ADJUSTMENT_RESULT_REVIEWED, "payroll.adjustment_result.review_initiated")
        await session.commit()
        return record

    async def decide_review(self, session: AsyncSession, *, context: AuthorizationContext, result_id: UUID, decision: AdjustmentResultDecision, reason_code: str, safe_note: str | None = None) -> PayrollAdjustmentResultReviewRecord:
        self._require(context, PayrollPermission.ADJUSTMENT_RESULT_REVIEW)
        if decision not in {AdjustmentResultDecision.ACCEPTED, AdjustmentResultDecision.REJECTED}:
            raise PayrollConflictError("adjustment result review decision is invalid")
        value = await self._locked(session, context, result_id)
        if value.lifecycle != "under_review":
            raise PayrollConflictError("adjustment result is not under review")
        value.lifecycle = "calculated" if decision is AdjustmentResultDecision.ACCEPTED else "rejected"
        record = await self._review(session, context, value, decision, reason_code, safe_note)
        self._stage(session, context, value, EventType.PAYROLL_ADJUSTMENT_RESULT_REVIEWED, f"payroll.adjustment_result.review_{decision.value}")
        await session.commit()
        return record

    async def approve(self, session: AsyncSession, *, context: AuthorizationContext, result_id: UUID, reason_code: str) -> PayrollAdjustmentResultReviewRecord:
        self._require(context, PayrollPermission.ADJUSTMENT_RESULT_APPROVE)
        value = await self._locked(session, context, result_id)
        if value.lifecycle == "approved":
            replay = await session.scalar(select(PayrollAdjustmentResultReviewRecord).where(PayrollAdjustmentResultReviewRecord.result_id == value.id, PayrollAdjustmentResultReviewRecord.reviewer_user_id == context.user.id, PayrollAdjustmentResultReviewRecord.decision == "approved", PayrollAdjustmentResultReviewRecord.reason_code == reason_code.strip()))
            if replay:
                return replay
        accepted = await session.scalar(select(PayrollAdjustmentResultReviewRecord.id).where(PayrollAdjustmentResultReviewRecord.result_id == value.id, PayrollAdjustmentResultReviewRecord.decision == "accepted"))
        if value.lifecycle != "calculated" or accepted is None:
            raise PayrollConflictError("review-accepted adjustment result is required")
        value.lifecycle, value.approved_by_user_id, value.approved_at = "approved", context.user.id, datetime.now(timezone.utc)
        record = await self._review(session, context, value, AdjustmentResultDecision.APPROVED, reason_code, None)
        self._stage(session, context, value, EventType.PAYROLL_ADJUSTMENT_RESULT_APPROVED, "payroll.adjustment_result.approved")
        await session.commit()
        return record

    async def apply(self, session: AsyncSession, *, context: AuthorizationContext, result_id: UUID, purpose: str, successor_authority_type: str) -> PayrollAdjustmentApplicationRecord:
        self._require(context, PayrollPermission.ADJUSTMENT_APPLY)
        value = await self._locked(session, context, result_id)
        expected = self._purpose(value.classification)
        if purpose != expected or not successor_authority_type.strip():
            raise PayrollConflictError("adjustment application purpose is invalid")
        existing = await session.scalar(select(PayrollAdjustmentApplicationRecord).where(PayrollAdjustmentApplicationRecord.result_id == value.id, PayrollAdjustmentApplicationRecord.purpose == purpose))
        content = {"company_id": str(value.company_id), "result_id": str(value.id), "result_digest": value.calculation_digest, "purpose": purpose, "successor_authority_type": successor_authority_type, "components": value.components}
        digest = canonical_digest(content)
        if existing:
            if existing.application_digest != digest:
                raise PayrollConflictError("adjustment application replay conflicts")
            return existing
        if value.lifecycle != "approved":
            raise PayrollConflictError("approved unapplied adjustment result is required")
        at = datetime.now(timezone.utc)
        record = PayrollAdjustmentApplicationRecord(company_id=value.company_id, result_id=value.id, purpose=purpose, successor_authority_type=successor_authority_type, result_digest=value.calculation_digest, authorized_components=value.components, application_digest=digest, applied_by_user_id=context.user.id, applied_at=at)
        session.add(record)
        value.lifecycle = "applied_to_successor_authority"
        await session.flush()
        self._stage(session, context, value, EventType.PAYROLL_ADJUSTMENT_RESULT_APPLIED, "payroll.adjustment_result.applied")
        await session.commit()
        return record

    async def result(self, session: AsyncSession, *, context: AuthorizationContext, result_id: UUID) -> PayrollAdjustmentResultRecord:
        self._require(context, PayrollPermission.ADJUSTMENT_RESULT_READ)
        value = await session.scalar(select(PayrollAdjustmentResultRecord).where(PayrollAdjustmentResultRecord.company_id == context.company.id, PayrollAdjustmentResultRecord.id == result_id))
        if value is None:
            raise PayrollConflictError("adjustment result was not found")
        self._verify(value, await self._predecessor_identity(session, value))
        return value

    @staticmethod
    def application_handoff(value: PayrollAdjustmentApplicationRecord) -> SuccessorApplication:
        return SuccessorApplication(value.result_id, value.result_digest, value.purpose, value.successor_authority_type, tuple(value.authorized_components), value.application_digest)

    async def _review(self, session: AsyncSession, context: AuthorizationContext, value: PayrollAdjustmentResultRecord, decision: AdjustmentResultDecision, reason_code: str, safe_note: str | None) -> PayrollAdjustmentResultReviewRecord:
        reason, note = reason_code.strip(), safe_note.strip() if safe_note else None
        if not reason or len(reason) > 80 or (note and (len(note) > 500 or "$" in note)):
            raise PayrollConflictError("adjustment result review evidence is unsafe")
        replay = await session.scalar(select(PayrollAdjustmentResultReviewRecord).where(PayrollAdjustmentResultReviewRecord.result_id == value.id, PayrollAdjustmentResultReviewRecord.reviewer_user_id == context.user.id, PayrollAdjustmentResultReviewRecord.decision == decision.value, PayrollAdjustmentResultReviewRecord.reason_code == reason, PayrollAdjustmentResultReviewRecord.safe_note == note))
        if replay:
            return replay
        sequence = (await session.scalar(select(func.count(PayrollAdjustmentResultReviewRecord.id)).where(PayrollAdjustmentResultReviewRecord.result_id == value.id)) or 0) + 1
        at = datetime.now(timezone.utc)
        digest = canonical_digest({"result_id": str(value.id), "result_digest": value.calculation_digest, "sequence": sequence, "reviewer": str(context.user.id), "decision": decision.value, "reason_code": reason, "safe_note": note, "reviewed_at": at.isoformat()})
        record = PayrollAdjustmentResultReviewRecord(company_id=value.company_id, result_id=value.id, sequence=sequence, reviewer_user_id=context.user.id, decision=decision.value, reason_code=reason, safe_note=note, result_digest=value.calculation_digest, review_digest=digest, reviewed_at=at)
        session.add(record)
        await session.flush()
        return record

    @staticmethod
    def _verify(value: PayrollAdjustmentResultRecord, predecessor_identity: str | None) -> None:
        del predecessor_identity  # lineage is persistence authority, not economic digest input
        components = tuple(CalculatedAdjustmentComponent(component=str(item["component"]), delta=Decimal(str(item["delta"])), currency=str(item["currency"]), recognition_effect=RecognitionEffect(str(item["recognition_effect"])), provider_id=str(item["provider_id"]), provider_version=str(item["provider_version"]), rule_evidence_digest=str(item["rule_evidence_digest"])) for item in value.components)
        from .adjustment_calculation import AdjustmentConsequenceType
        candidate = PayrollAdjustmentCalculationCandidate(result_identity=value.result_identity, definition_version=value.calculation_version, company_id=value.company_id, employee_id=value.employee_id, original_pay_period_id=value.original_pay_period_id, correction_pay_period_id=value.correction_pay_period_id, adjustment_id=value.adjustment_id, adjustment_digest=value.adjustment_digest, source_type=value.source_type, source_id=value.source_id, source_digest=value.source_digest, classification=PayrollCorrectionType(value.classification), currency=value.currency, components=components, consequences=tuple(AdjustmentConsequenceType(item) for item in value.consequences), calculation_digest=value.calculation_digest, calculated_at=value.calculated_at)
        candidate.verify()

    @staticmethod
    def _purpose(classification: str) -> str:
        mapping = {"pre_payment_payroll_correction": "successor_payroll", "retroactive_earnings": "successor_payroll", "off_cycle_payroll": "off_cycle_payroll", "tax_correction": "successor_tax_calculation", "deduction_correction": "successor_deduction_calculation", "payment_return": "payment_recovery", "payment_rejection": "payment_reissue", "payment_reversal": "payment_recovery", "settlement_correction": "settlement_reconciliation", "accounting_adjustment_required": "accounting_adjustment"}
        return mapping[classification]

    async def _locked(self, session: AsyncSession, context: AuthorizationContext, result_id: UUID) -> PayrollAdjustmentResultRecord:
        value = await session.scalar(select(PayrollAdjustmentResultRecord).where(PayrollAdjustmentResultRecord.company_id == context.company.id, PayrollAdjustmentResultRecord.id == result_id).with_for_update())
        if value is None:
            raise PayrollConflictError("adjustment result was not found")
        return value

    async def _predecessor_identity(self, session: AsyncSession, value: PayrollAdjustmentResultRecord) -> str | None:
        if value.supersedes_result_id is None:
            return None
        return await session.scalar(select(PayrollAdjustmentResultRecord.result_identity).where(PayrollAdjustmentResultRecord.id == value.supersedes_result_id))

    @staticmethod
    def _require(context: AuthorizationContext, permission: str) -> None:
        if not context.has_permission(permission):
            raise PayrollAuthorizationError("adjustment result permission denied")

    def _stage(self, session: AsyncSession, context: AuthorizationContext, value: PayrollAdjustmentResultRecord, event: EventType, action: str) -> None:
        details: dict[str, object] = {"result_id": str(value.id), "result_digest": value.calculation_digest, "adjustment_id": str(value.adjustment_id), "classification": value.classification, "lifecycle": value.lifecycle}
        BusinessEventService.stage(session, BusinessEventCreate(event_type=event, entity_type="payroll_adjustment_result", entity_id=value.id, company_id=value.company_id, user_id=context.user.id, payload=details))
        self._audit.stage(session, AuditEntry(action=action, resource_type="payroll_adjustment_result", actor_user_id=context.user.id, company_id=value.company_id, resource_id=value.id, details=details))
