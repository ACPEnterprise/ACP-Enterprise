"""Immutable review authority for verified tax/deduction calculation candidates."""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import cast
from uuid import UUID

from sqlalchemy import Select, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, AuditService, audit_service
from app.platform.permissions.authorization import AuthorizationContext

from .contracts import PayrollAuthorizationError, PayrollConflictError, canonical_digest
from .models import (
    PayrollGrossCalculationResultRecord,
    PayrollTaxDeductionResultRecord,
    PayrollTaxDeductionReviewRecord,
)
from .permissions import PayrollPermission
from .tax_authority import TaxDeductionAdmissionResult, TaxDeductionAdmissionState
from .tax_calculation import (
    ComponentKind,
    TaxDeductionCalculationResult,
    TaxDeductionComponent,
)


class TaxResultLifecycle(StrEnum):
    CALCULATED = "calculated"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    VOIDED = "voided"


class TaxResultReviewState(StrEnum):
    NOT_STARTED = "not_started"
    UNDER_REVIEW = "under_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class TaxReviewDecision(StrEnum):
    INITIATED = "initiated"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class TaxPeriodResultStatus:
    employee_id: UUID
    result_id: UUID | None
    status: str
    evidence_digest: str


class PayrollTaxDeductionResultService:
    def __init__(self, *, audit: AuditService = audit_service) -> None:
        self._audit = audit

    async def persist_candidate(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        candidate: TaxDeductionCalculationResult,
        admission: TaxDeductionAdmissionResult,
    ) -> PayrollTaxDeductionResultRecord:
        self._require(context, PayrollPermission.TAX_CALCULATION_EXECUTE)
        candidate.verify()
        admission.verify()
        if admission.state not in {
            TaxDeductionAdmissionState.READY,
            TaxDeductionAdmissionState.NOT_APPLICABLE,
        }:
            raise PayrollConflictError("blocked tax/deduction admission cannot persist")
        if admission.state is TaxDeductionAdmissionState.NOT_APPLICABLE and candidate.components:
            raise PayrollConflictError("not-applicable admission cannot persist components")
        if (
            candidate.company_id != context.company.id
            or admission.company_id != candidate.company_id
            or admission.employee_id != candidate.employee_id
            or admission.gross_result_id != candidate.gross_result_id
            or admission.gross_calculation_digest != candidate.gross_calculation_digest
            or admission.admission_digest != candidate.admission_digest
        ):
            raise PayrollConflictError("tax result admission scope mismatch")
        gross = await session.scalar(
            select(PayrollGrossCalculationResultRecord).where(
                PayrollGrossCalculationResultRecord.company_id == context.company.id,
                PayrollGrossCalculationResultRecord.id == candidate.gross_result_id,
                PayrollGrossCalculationResultRecord.employee_id == candidate.employee_id,
                PayrollGrossCalculationResultRecord.pay_period_id == candidate.pay_period_id,
                PayrollGrossCalculationResultRecord.calculation_digest == candidate.gross_calculation_digest,
                PayrollGrossCalculationResultRecord.currency == candidate.currency,
                PayrollGrossCalculationResultRecord.gross_pay_total == candidate.gross_pay,
                PayrollGrossCalculationResultRecord.lifecycle == "approved",
            )
        )
        if gross is None:
            raise PayrollConflictError("approved gross-pay evidence is unavailable")
        await self._subject_lock(session, candidate.company_id, candidate.employee_id, candidate.pay_period_id)
        existing = await session.scalar(
            select(PayrollTaxDeductionResultRecord).where(
                PayrollTaxDeductionResultRecord.company_id == context.company.id,
                PayrollTaxDeductionResultRecord.calculation_digest == candidate.calculation_digest,
            )
        )
        if existing is not None:
            self._verify_record(existing, candidate.supersedes_result_id)
            if existing.result_identity != candidate.result_id:
                raise PayrollConflictError("tax result persistence identity conflict")
            return existing
        active = await session.scalar(self._active_query(candidate).with_for_update())
        prior = None
        if candidate.supersedes_result_id:
            prior = await session.scalar(
                select(PayrollTaxDeductionResultRecord).where(
                    PayrollTaxDeductionResultRecord.company_id == context.company.id,
                    PayrollTaxDeductionResultRecord.result_identity == candidate.supersedes_result_id,
                ).with_for_update()
            )
            if prior is None or active is None or prior.id != active.id:
                raise PayrollConflictError("tax result supersession lineage conflict")
            prior.lifecycle = TaxResultLifecycle.SUPERSEDED.value
            await session.flush()
        elif active is not None:
            raise PayrollConflictError("active tax/deduction result already exists")
        value = PayrollTaxDeductionResultRecord(
            company_id=candidate.company_id,
            employee_id=candidate.employee_id,
            pay_period_id=candidate.pay_period_id,
            gross_result_id=candidate.gross_result_id,
            gross_calculation_digest=candidate.gross_calculation_digest,
            result_identity=candidate.result_id,
            calculation_version=candidate.definition_version,
            currency=candidate.currency,
            admission_digest=candidate.admission_digest,
            authority_evidence=[item.canonical_content() for item in admission.resolutions],
            components=[item.canonical_content() for item in candidate.components],
            gross_pay=candidate.gross_pay,
            employee_tax_total=candidate.total_employee_taxes,
            employee_deduction_total=candidate.total_employee_deductions,
            employer_contribution_total=candidate.total_employer_contributions,
            net_pay_candidate=candidate.net_pay_candidate,
            money_version=candidate.money_version,
            calculation_digest=candidate.calculation_digest,
            calculated_at=candidate.calculated_at,
            created_by_user_id=context.user.id,
            lifecycle=TaxResultLifecycle.CALCULATED.value,
            review_state=TaxResultReviewState.NOT_STARTED.value,
            supersedes_result_id=prior.id if prior else None,
        )
        session.add(value)
        await session.flush()
        self._verify_record(value, candidate.supersedes_result_id)
        if prior:
            self._stage(session, context, prior, EventType.PAYROLL_TAX_RESULT_SUPERSEDED, "payroll.tax_result.superseded")
        self._stage(session, context, value, EventType.PAYROLL_TAX_RESULT_PERSISTED, "payroll.tax_result.persisted")
        await session.commit()
        return value

    async def initiate_review(self, session: AsyncSession, *, context: AuthorizationContext, result_id: UUID, reason_code: str, safe_note: str | None = None) -> PayrollTaxDeductionReviewRecord:
        self._require(context, PayrollPermission.TAX_RESULT_REVIEW)
        value = await self._locked_result(session, context, result_id)
        if value.lifecycle not in {TaxResultLifecycle.CALCULATED.value, TaxResultLifecycle.REJECTED.value}:
            raise PayrollConflictError("tax result cannot enter review")
        value.lifecycle = TaxResultLifecycle.UNDER_REVIEW.value
        value.review_state = TaxResultReviewState.UNDER_REVIEW.value
        record = await self._review(session, context, value, TaxReviewDecision.INITIATED, reason_code, safe_note)
        self._stage(session, context, value, EventType.PAYROLL_TAX_RESULT_REVIEW_INITIATED, "payroll.tax_result.review_initiated")
        await session.commit()
        return record

    async def decide_review(self, session: AsyncSession, *, context: AuthorizationContext, result_id: UUID, decision: TaxReviewDecision, reason_code: str, safe_note: str | None = None) -> PayrollTaxDeductionReviewRecord:
        self._require(context, PayrollPermission.TAX_RESULT_REVIEW)
        if decision not in {TaxReviewDecision.ACCEPTED, TaxReviewDecision.REJECTED}:
            raise PayrollConflictError("tax result review decision is invalid")
        value = await self._locked_result(session, context, result_id)
        if value.lifecycle != TaxResultLifecycle.UNDER_REVIEW.value:
            raise PayrollConflictError("tax result is not under review")
        accepted = decision is TaxReviewDecision.ACCEPTED
        value.lifecycle = TaxResultLifecycle.APPROVED.value if accepted else TaxResultLifecycle.REJECTED.value
        value.review_state = TaxResultReviewState.ACCEPTED.value if accepted else TaxResultReviewState.REJECTED.value
        record = await self._review(session, context, value, decision, reason_code, safe_note)
        event = EventType.PAYROLL_TAX_RESULT_REVIEW_ACCEPTED if accepted else EventType.PAYROLL_TAX_RESULT_REVIEW_REJECTED
        self._stage(session, context, value, event, f"payroll.tax_result.review_{decision.value}")
        await session.commit()
        return record

    async def result(self, session: AsyncSession, *, context: AuthorizationContext, result_id: UUID) -> PayrollTaxDeductionResultRecord:
        self._require(context, PayrollPermission.TAX_RESULT_READ)
        value = await session.scalar(select(PayrollTaxDeductionResultRecord).where(PayrollTaxDeductionResultRecord.company_id == context.company.id, PayrollTaxDeductionResultRecord.id == result_id))
        if value is None:
            raise PayrollConflictError("tax result was not found")
        predecessor = await self._predecessor_identity(session, value)
        self._verify_record(value, predecessor)
        return value

    async def period_results(self, session: AsyncSession, *, context: AuthorizationContext, pay_period_id: UUID, blocked_admissions: tuple[TaxDeductionAdmissionResult, ...] = ()) -> tuple[TaxPeriodResultStatus, ...]:
        self._require(context, PayrollPermission.TAX_RESULT_READ)
        values = (await session.scalars(select(PayrollTaxDeductionResultRecord).where(PayrollTaxDeductionResultRecord.company_id == context.company.id, PayrollTaxDeductionResultRecord.pay_period_id == pay_period_id))).all()
        statuses = [TaxPeriodResultStatus(v.employee_id, v.id, v.lifecycle, v.calculation_digest) for v in values]
        for admission in blocked_admissions:
            admission.verify()
            if admission.company_id != context.company.id or admission.state not in {TaxDeductionAdmissionState.MISSING, TaxDeductionAdmissionState.EXPIRED, TaxDeductionAdmissionState.UNAPPROVED, TaxDeductionAdmissionState.CONFLICTING}:
                raise PayrollConflictError("blocked tax admission evidence is invalid")
            statuses.append(TaxPeriodResultStatus(admission.employee_id, None, admission.state.value, admission.admission_digest))
        return tuple(sorted(statuses, key=lambda item: str(item.employee_id)))

    async def history(self, session: AsyncSession, *, context: AuthorizationContext, employee_id: UUID, pay_period_id: UUID) -> tuple[PayrollTaxDeductionResultRecord, ...]:
        self._require(context, PayrollPermission.TAX_RESULT_READ)
        values = await session.scalars(select(PayrollTaxDeductionResultRecord).where(PayrollTaxDeductionResultRecord.company_id == context.company.id, PayrollTaxDeductionResultRecord.employee_id == employee_id, PayrollTaxDeductionResultRecord.pay_period_id == pay_period_id).order_by(PayrollTaxDeductionResultRecord.created_at))
        return tuple(values.all())

    async def _review(self, session: AsyncSession, context: AuthorizationContext, value: PayrollTaxDeductionResultRecord, decision: TaxReviewDecision, reason_code: str, safe_note: str | None) -> PayrollTaxDeductionReviewRecord:
        reason, note = reason_code.strip(), safe_note.strip() if safe_note else None
        if not reason or len(reason) > 80 or (note and (len(note) > 500 or "$" in note)):
            raise PayrollConflictError("tax result review evidence is unsafe")
        sequence = (await session.scalar(select(func.count(PayrollTaxDeductionReviewRecord.id)).where(PayrollTaxDeductionReviewRecord.result_id == value.id)) or 0) + 1
        at = datetime.now(timezone.utc)
        digest = canonical_digest({"result_id": str(value.id), "result_digest": value.calculation_digest, "sequence": sequence, "reviewer": str(context.user.id), "decision": decision.value, "reason_code": reason, "safe_note": note, "reviewed_at": at.isoformat()})
        record = PayrollTaxDeductionReviewRecord(company_id=context.company.id, result_id=value.id, review_sequence=sequence, reviewer_user_id=context.user.id, decision=decision.value, reason_code=reason, safe_note=note, result_digest=value.calculation_digest, review_digest=digest, reviewed_at=at)
        session.add(record)
        await session.flush()
        return record

    @staticmethod
    def _verify_record(value: PayrollTaxDeductionResultRecord, supersedes_identity: str | None) -> None:
        components = tuple(TaxDeductionComponent(component_key=str(c["component_key"]), kind=ComponentKind(str(c["kind"])), responsibility=str(c["responsibility"]), authority_id=UUID(str(c["authority_id"])), authority_digest=str(c["authority_digest"]), provider_id=str(c["provider_id"]) if c.get("provider_id") else None, provider_version=str(c["provider_version"]) if c.get("provider_version") else None, jurisdiction_reference=str(c["jurisdiction_reference"]) if c.get("jurisdiction_reference") else None, calculation_basis=str(c["calculation_basis"]), basis_amount=Decimal(str(c["basis_amount"])), amount=Decimal(str(c["amount"])), currency=str(c["currency"]), priority=int(cast(int | str, c["priority"])), rounding_rule=str(c["rounding_rule"]), evidence_digest=str(c["evidence_digest"])) for c in value.components)
        TaxDeductionCalculationResult(result_id=value.result_identity, definition_version=value.calculation_version, company_id=value.company_id, employee_id=value.employee_id, pay_period_id=value.pay_period_id, gross_result_id=value.gross_result_id, gross_calculation_digest=value.gross_calculation_digest, currency=value.currency, admission_digest=value.admission_digest, components=components, gross_pay=value.gross_pay, total_employee_taxes=value.employee_tax_total, total_employee_deductions=value.employee_deduction_total, total_employer_contributions=value.employer_contribution_total, net_pay_candidate=value.net_pay_candidate, money_version=value.money_version, calculation_digest=value.calculation_digest, calculated_at=value.calculated_at, supersedes_result_id=supersedes_identity).verify()

    async def _predecessor_identity(self, session: AsyncSession, value: PayrollTaxDeductionResultRecord) -> str | None:
        if value.supersedes_result_id is None:
            return None
        return await session.scalar(select(PayrollTaxDeductionResultRecord.result_identity).where(PayrollTaxDeductionResultRecord.id == value.supersedes_result_id))

    async def _locked_result(self, session: AsyncSession, context: AuthorizationContext, result_id: UUID) -> PayrollTaxDeductionResultRecord:
        value = await session.scalar(select(PayrollTaxDeductionResultRecord).where(PayrollTaxDeductionResultRecord.company_id == context.company.id, PayrollTaxDeductionResultRecord.id == result_id).with_for_update())
        if value is None:
            raise PayrollConflictError("tax result was not found")
        return value

    @staticmethod
    async def _subject_lock(session: AsyncSession, company_id: UUID, employee_id: UUID, pay_period_id: UUID) -> None:
        await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"payroll-tax:{company_id}:{employee_id}:{pay_period_id}"})

    @staticmethod
    def _active_query(candidate: TaxDeductionCalculationResult) -> Select[tuple[PayrollTaxDeductionResultRecord]]:
        return select(PayrollTaxDeductionResultRecord).where(PayrollTaxDeductionResultRecord.company_id == candidate.company_id, PayrollTaxDeductionResultRecord.employee_id == candidate.employee_id, PayrollTaxDeductionResultRecord.pay_period_id == candidate.pay_period_id, PayrollTaxDeductionResultRecord.lifecycle.in_(("calculated", "under_review", "approved")))

    @staticmethod
    def _require(context: AuthorizationContext, permission: str) -> None:
        if not context.has_permission(permission):
            raise PayrollAuthorizationError("tax result permission denied")

    def _stage(self, session: AsyncSession, context: AuthorizationContext, value: PayrollTaxDeductionResultRecord, event_type: EventType, action: str) -> None:
        details: dict[str, object] = {"result_id": value.result_identity, "calculation_digest": value.calculation_digest, "lifecycle": value.lifecycle}
        BusinessEventService.stage(session, BusinessEventCreate(event_type=event_type, entity_type="payroll_tax_deduction_result", entity_id=value.id, company_id=context.company.id, user_id=context.user.id, payload=details))
        self._audit.stage(session, AuditEntry(action=action, resource_type="payroll_tax_deduction_result", actor_user_id=context.user.id, company_id=context.company.id, resource_id=value.id, details=details))


payroll_tax_deduction_result_service = PayrollTaxDeductionResultService()
