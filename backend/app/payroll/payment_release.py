"""Protected Payroll payment authority; never executes or settles payment."""

from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
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

from .contracts import PayrollAuthorizationError, PayrollConflictError, canonical_digest
from .models import (
    PayrollPaymentDestinationVersion,
    PayrollPaymentInstructionRecord,
    PayrollPaymentReleaseRecord,
    PayrollPaymentReleaseReviewRecord,
    PayrollProtectedInputEnvelope,
    PayrollRunMemberRecord,
    PayrollRunRecord,
    PayrollTaxDeductionResultRecord,
)
from .permissions import PayrollPermission
from .tax_authority import ProtectedPayrollInputCipher

PAYMENT_DESTINATION_VERSION = "payroll.payment-destination.v1"
PAYMENT_RELEASE_VERSION = "payroll.payment-release.v1"
PAYMENT_EXECUTION_HANDOFF_VERSION = "payroll.payment-execution-handoff.v1"


class PaymentMethod(StrEnum):
    DIRECT_DEPOSIT = "direct_deposit"
    PAPER_CHECK = "paper_check"
    OTHER = "other"


class DestinationAdmissionState(StrEnum):
    READY = "ready"
    MISSING = "missing"
    UNVERIFIED = "unverified"
    EXPIRED = "expired"
    CONFLICTING = "conflicting"
    REVOKED = "revoked"
    NOT_APPLICABLE = "not_applicable"


class PaymentInstructionDisposition(StrEnum):
    READY = "ready"
    BLOCKED = "blocked"
    EXCLUDED = "excluded"
    NOT_APPLICABLE = "not_applicable"


class PaymentReleaseLifecycle(StrEnum):
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    APPROVED_FOR_RELEASE = "approved_for_release"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    VOIDED = "voided"


class PaymentReleaseReviewDecision(StrEnum):
    INITIATED = "initiated"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    APPROVED = "approved"


@dataclass(frozen=True)
class DraftPaymentDestination:
    employee_id: UUID
    destination_version: int
    method: PaymentMethod
    destination_reference: str
    masked_display: str
    verification_evidence_digest: str
    effective_start: date
    effective_end: date | None
    protected_payload: dict[str, object] | None
    audit_reason: str


@dataclass(frozen=True)
class DestinationResolution:
    employee_id: UUID
    state: DestinationAdmissionState
    destination_id: UUID | None
    destination_digest: str | None
    method: PaymentMethod | None
    protected_reference: str | None
    evidence_digest: str

    def verify(self) -> None:
        expected = canonical_digest(
            {
                "employee_id": str(self.employee_id),
                "state": self.state.value,
                "destination_id": str(self.destination_id) if self.destination_id else None,
                "destination_digest": self.destination_digest,
                "method": self.method.value if self.method else None,
                "protected_reference": self.protected_reference,
            }
        )
        if expected != self.evidence_digest:
            raise PayrollConflictError("payment destination admission digest is invalid")


@dataclass(frozen=True)
class PaymentInstruction:
    employee_id: UUID
    disposition: PaymentInstructionDisposition
    run_member_digest: str
    tax_result_id: UUID | None
    tax_result_digest: str | None
    destination_id: UUID | None
    destination_digest: str | None
    method: PaymentMethod | None
    protected_destination_reference: str | None
    amount: Decimal
    currency: str
    blocker_evidence_digest: str | None
    instruction_identity: str
    instruction_digest: str

    def canonical_content(self) -> dict[str, object]:
        return {
            "employee_id": str(self.employee_id),
            "disposition": self.disposition.value,
            "run_member_digest": self.run_member_digest,
            "tax_result_id": str(self.tax_result_id) if self.tax_result_id else None,
            "tax_result_digest": self.tax_result_digest,
            "destination_id": str(self.destination_id) if self.destination_id else None,
            "destination_digest": self.destination_digest,
            "method": self.method.value if self.method else None,
            "protected_destination_reference": self.protected_destination_reference,
            "amount": str(self.amount),
            "currency": self.currency,
            "blocker_evidence_digest": self.blocker_evidence_digest,
        }


@dataclass(frozen=True)
class PaymentReleaseCandidate:
    company_id: UUID
    payroll_run_id: UUID
    payroll_run_digest: str
    pay_period_id: UUID
    definition_version: str
    currency: str
    instructions: tuple[PaymentInstruction, ...]
    aggregate_release_amount: Decimal
    package_identity: str
    package_digest: str
    assembled_at: datetime
    supersedes_package_identity: str | None = None

    def canonical_content(self) -> dict[str, object]:
        return {
            "company_id": str(self.company_id),
            "payroll_run_id": str(self.payroll_run_id),
            "payroll_run_digest": self.payroll_run_digest,
            "pay_period_id": str(self.pay_period_id),
            "definition_version": self.definition_version,
            "currency": self.currency,
            "instructions": tuple(item.canonical_content() for item in self.instructions),
            "aggregate_release_amount": str(self.aggregate_release_amount),
            "supersedes_package_identity": self.supersedes_package_identity,
        }

    def verify(self) -> None:
        digest = canonical_digest(self.canonical_content())
        if self.package_digest != digest or self.package_identity != f"payroll-payment-release:{digest}":
            raise PayrollConflictError("payment release identity or digest is invalid")
        if len({item.employee_id for item in self.instructions}) != len(self.instructions):
            raise PayrollConflictError("payment release contains duplicate Employees")
        for item in self.instructions:
            item_digest = canonical_digest(item.canonical_content())
            if item.instruction_digest != item_digest or item.instruction_identity != f"payroll-payment-instruction:{item_digest}":
                raise PayrollConflictError("payment instruction identity is invalid")
        total = sum((item.amount for item in self.instructions if item.disposition is PaymentInstructionDisposition.READY), Decimal(0))
        if total != self.aggregate_release_amount:
            raise PayrollConflictError("payment release total reconciliation failed")


@dataclass(frozen=True)
class PaymentExecutionHandoff:
    definition_version: str
    company_id: UUID
    pay_period_id: UUID
    release_id: UUID
    package_identity: str
    package_digest: str
    currency: str
    instruction_identities: tuple[str, ...]
    aggregate_release_amount: Decimal
    approval_evidence_digest: str
    execution_idempotency_identity: str


class PayrollPaymentReleaseService:
    def __init__(self, *, cipher: ProtectedPayrollInputCipher | None = None, audit: AuditService = audit_service) -> None:
        self._cipher = cipher
        self._audit = audit

    async def create_destination(self, session: AsyncSession, *, context: AuthorizationContext, draft: DraftPaymentDestination) -> PayrollPaymentDestinationVersion:
        self._require(context, PayrollPermission.PAYMENT_INSTRUCTION_MANAGE)
        if not draft.destination_reference.strip() or not draft.masked_display.strip() or draft.effective_end and draft.effective_end <= draft.effective_start:
            raise PayrollConflictError("payment destination input is invalid")
        envelope_id = None
        protected_digest = None
        if draft.protected_payload is not None:
            if self._cipher is None:
                raise PayrollConflictError("protected payment destination key is unavailable")
            key_id, nonce, ciphertext, protected_digest = self._cipher.encrypt(company_id=context.company.id, payload=draft.protected_payload)
            envelope = PayrollProtectedInputEnvelope(company_id=context.company.id, key_id=key_id, nonce=nonce, ciphertext=ciphertext, content_digest=protected_digest, created_by_user_id=context.user.id)
            session.add(envelope)
            await session.flush()
            envelope_id = envelope.id
        canonical = {"company_id": str(context.company.id), "employee_id": str(draft.employee_id), "destination_version": draft.destination_version, "definition_version": PAYMENT_DESTINATION_VERSION, "method": draft.method.value, "destination_reference": draft.destination_reference, "protected_digest": protected_digest, "masked_display": draft.masked_display, "verification_evidence_digest": draft.verification_evidence_digest, "effective_start": draft.effective_start.isoformat(), "effective_end": draft.effective_end.isoformat() if draft.effective_end else None}
        value = PayrollPaymentDestinationVersion(company_id=context.company.id, employee_id=draft.employee_id, destination_version=draft.destination_version, definition_version=PAYMENT_DESTINATION_VERSION, method_type=draft.method.value, destination_reference=draft.destination_reference, protected_envelope_id=envelope_id, masked_display=draft.masked_display, verification_evidence_digest=draft.verification_evidence_digest, effective_start=draft.effective_start, effective_end=draft.effective_end, lifecycle="draft", authority_digest=canonical_digest(canonical), supersedes_destination_id=None, created_by_user_id=context.user.id, approved_by_user_id=None, approved_at=None, audit_reason=draft.audit_reason)
        session.add(value)
        await session.flush()
        self._stage_destination(session, context, value, EventType.PAYROLL_PAYMENT_DESTINATION_CREATED, "payroll.payment_destination.created")
        await session.commit()
        return value

    async def approve_destination(self, session: AsyncSession, *, context: AuthorizationContext, destination_id: UUID) -> PayrollPaymentDestinationVersion:
        self._require(context, PayrollPermission.PAYMENT_INSTRUCTION_MANAGE)
        value = await session.scalar(select(PayrollPaymentDestinationVersion).where(PayrollPaymentDestinationVersion.company_id == context.company.id, PayrollPaymentDestinationVersion.id == destination_id).with_for_update())
        if value is None or value.lifecycle != "draft":
            raise PayrollConflictError("draft payment destination is unavailable")
        value.lifecycle, value.approved_by_user_id, value.approved_at = "approved", context.user.id, datetime.now(timezone.utc)
        self._stage_destination(session, context, value, EventType.PAYROLL_PAYMENT_DESTINATION_APPROVED, "payroll.payment_destination.approved")
        await session.commit()
        return value

    async def resolve_destination(self, session: AsyncSession, *, company_id: UUID, employee_id: UUID, as_of_date: date) -> DestinationResolution:
        values = tuple((await session.scalars(select(PayrollPaymentDestinationVersion).where(PayrollPaymentDestinationVersion.company_id == company_id, PayrollPaymentDestinationVersion.employee_id == employee_id, PayrollPaymentDestinationVersion.effective_start <= as_of_date, (PayrollPaymentDestinationVersion.effective_end.is_(None) | (PayrollPaymentDestinationVersion.effective_end > as_of_date))))).all())
        approved = tuple(item for item in values if item.lifecycle == "approved")
        if len(approved) > 1:
            return self._resolution(employee_id, DestinationAdmissionState.CONFLICTING)
        if len(approved) == 1:
            item = approved[0]
            return self._resolution(employee_id, DestinationAdmissionState.READY, item)
        state = DestinationAdmissionState.MISSING
        if any(item.lifecycle == "revoked" for item in values):
            state = DestinationAdmissionState.REVOKED
        elif any(item.lifecycle == "draft" for item in values):
            state = DestinationAdmissionState.UNVERIFIED
        return self._resolution(employee_id, state)

    async def assemble_candidate(self, session: AsyncSession, *, context: AuthorizationContext, payroll_run_id: UUID, destinations: dict[UUID, DestinationResolution], assembled_at: datetime, supersedes_package_identity: str | None = None) -> PaymentReleaseCandidate:
        self._require(context, PayrollPermission.PAYMENT_RELEASE_ASSEMBLE)
        run = await session.scalar(select(PayrollRunRecord).where(PayrollRunRecord.company_id == context.company.id, PayrollRunRecord.id == payroll_run_id, PayrollRunRecord.lifecycle == "approved"))
        if run is None:
            raise PayrollConflictError("approved Payroll run is required")
        members = tuple((await session.scalars(select(PayrollRunMemberRecord).where(PayrollRunMemberRecord.run_id == run.id, PayrollRunMemberRecord.disposition == "ready").order_by(PayrollRunMemberRecord.employee_id))).all())
        if set(destinations) != {item.employee_id for item in members}:
            raise PayrollConflictError("payment release payable population is incomplete")
        instructions: list[PaymentInstruction] = []
        for member in members:
            resolution = destinations[member.employee_id]
            resolution.verify()
            if resolution.employee_id != member.employee_id:
                raise PayrollConflictError("payment destination Employee scope mismatch")
            tax = await session.scalar(select(PayrollTaxDeductionResultRecord).where(PayrollTaxDeductionResultRecord.company_id == run.company_id, PayrollTaxDeductionResultRecord.id == member.tax_result_id, PayrollTaxDeductionResultRecord.calculation_digest == member.tax_result_digest, PayrollTaxDeductionResultRecord.lifecycle == "approved", PayrollTaxDeductionResultRecord.currency == run.currency))
            if tax is None:
                raise PayrollConflictError("approved net-pay evidence is unavailable")
            if resolution.state is DestinationAdmissionState.READY:
                disposition, amount, blocker = PaymentInstructionDisposition.READY, tax.net_pay_candidate, None
            else:
                disposition, amount, blocker = PaymentInstructionDisposition.BLOCKED, Decimal("0.00"), resolution.evidence_digest
            provisional = PaymentInstruction(member.employee_id, disposition, member.membership_digest, tax.id, tax.calculation_digest, resolution.destination_id, resolution.destination_digest, resolution.method, resolution.protected_reference, amount, run.currency, blocker, "", "")
            digest = canonical_digest(provisional.canonical_content())
            instructions.append(replace(provisional, instruction_identity=f"payroll-payment-instruction:{digest}", instruction_digest=digest))
        ordered = tuple(instructions)
        provisional_package = PaymentReleaseCandidate(run.company_id, run.id, run.run_digest, run.pay_period_id, PAYMENT_RELEASE_VERSION, run.currency, ordered, sum((item.amount for item in ordered if item.disposition is PaymentInstructionDisposition.READY), Decimal(0)), "", "", assembled_at, supersedes_package_identity)
        digest = canonical_digest(provisional_package.canonical_content())
        result = replace(provisional_package, package_identity=f"payroll-payment-release:{digest}", package_digest=digest)
        result.verify()
        return result

    async def persist_candidate(self, session: AsyncSession, *, context: AuthorizationContext, candidate: PaymentReleaseCandidate) -> PayrollPaymentReleaseRecord:
        self._require(context, PayrollPermission.PAYMENT_RELEASE_ASSEMBLE)
        candidate.verify()
        if candidate.company_id != context.company.id:
            raise PayrollConflictError("payment release Company scope mismatch")
        await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"payroll-payment-release:{candidate.company_id}:{candidate.payroll_run_id}"})
        existing = await session.scalar(select(PayrollPaymentReleaseRecord).where(PayrollPaymentReleaseRecord.company_id == context.company.id, PayrollPaymentReleaseRecord.package_digest == candidate.package_digest))
        if existing:
            return existing
        active = await session.scalar(select(PayrollPaymentReleaseRecord).where(PayrollPaymentReleaseRecord.company_id == context.company.id, PayrollPaymentReleaseRecord.payroll_run_id == candidate.payroll_run_id, PayrollPaymentReleaseRecord.lifecycle.in_(("draft", "under_review", "approved_for_release"))).with_for_update())
        prior = None
        if candidate.supersedes_package_identity:
            prior = await session.scalar(select(PayrollPaymentReleaseRecord).where(PayrollPaymentReleaseRecord.company_id == context.company.id, PayrollPaymentReleaseRecord.package_identity == candidate.supersedes_package_identity).with_for_update())
            if prior is None or active is None or prior.id != active.id or prior.execution_started_at is not None:
                raise PayrollConflictError("payment release supersession lineage conflict")
            prior.lifecycle = "superseded"
            await session.flush()
        elif active:
            raise PayrollConflictError("active payment release already exists")
        value = PayrollPaymentReleaseRecord(company_id=candidate.company_id, payroll_run_id=candidate.payroll_run_id, payroll_run_digest=candidate.payroll_run_digest, pay_period_id=candidate.pay_period_id, definition_version=candidate.definition_version, currency=candidate.currency, package_identity=candidate.package_identity, package_digest=candidate.package_digest, aggregate_release_amount=candidate.aggregate_release_amount, assembled_by_user_id=context.user.id, assembled_at=candidate.assembled_at, lifecycle="draft", review_state="not_started", supersedes_release_id=prior.id if prior else None)
        session.add(value)
        await session.flush()
        for item in candidate.instructions:
            session.add(PayrollPaymentInstructionRecord(company_id=value.company_id, release_id=value.id, employee_id=item.employee_id, disposition=item.disposition.value, run_member_digest=item.run_member_digest, tax_result_id=item.tax_result_id, tax_result_digest=item.tax_result_digest, destination_id=item.destination_id, destination_digest=item.destination_digest, method_type=item.method.value if item.method else None, protected_destination_reference=item.protected_destination_reference, amount=item.amount, currency=item.currency, blocker_evidence_digest=item.blocker_evidence_digest, instruction_identity=item.instruction_identity, instruction_digest=item.instruction_digest))
        await session.flush()
        if prior:
            self._stage_release(session, context, prior, EventType.PAYROLL_PAYMENT_RELEASE_SUPERSEDED, "payroll.payment_release.superseded")
        self._stage_release(session, context, value, EventType.PAYROLL_PAYMENT_RELEASE_ASSEMBLED, "payroll.payment_release.assembled")
        await session.commit()
        return value

    async def initiate_review(self, session: AsyncSession, *, context: AuthorizationContext, release_id: UUID, reason_code: str) -> PayrollPaymentReleaseReviewRecord:
        self._require(context, PayrollPermission.PAYMENT_RELEASE_REVIEW)
        value = await self._locked_release(session, context, release_id)
        if value.lifecycle not in {"draft", "rejected"}:
            raise PayrollConflictError("payment release cannot enter review")
        value.lifecycle, value.review_state = "under_review", "under_review"
        record = await self._review(session, context, value, PaymentReleaseReviewDecision.INITIATED, reason_code)
        self._stage_release(session, context, value, EventType.PAYROLL_PAYMENT_RELEASE_REVIEWED, "payroll.payment_release.review_initiated")
        await session.commit()
        return record

    async def decide_review(self, session: AsyncSession, *, context: AuthorizationContext, release_id: UUID, decision: PaymentReleaseReviewDecision, reason_code: str) -> PayrollPaymentReleaseReviewRecord:
        self._require(context, PayrollPermission.PAYMENT_RELEASE_REVIEW)
        if decision not in {PaymentReleaseReviewDecision.ACCEPTED, PaymentReleaseReviewDecision.REJECTED}:
            raise PayrollConflictError("payment release review decision is invalid")
        value = await self._locked_release(session, context, release_id)
        if value.lifecycle != "under_review":
            raise PayrollConflictError("payment release is not under review")
        value.lifecycle, value.review_state = ("draft", "accepted") if decision is PaymentReleaseReviewDecision.ACCEPTED else ("rejected", "rejected")
        record = await self._review(session, context, value, decision, reason_code)
        self._stage_release(session, context, value, EventType.PAYROLL_PAYMENT_RELEASE_REVIEWED, f"payroll.payment_release.review_{decision.value}")
        await session.commit()
        return record

    async def approve_release(self, session: AsyncSession, *, context: AuthorizationContext, release_id: UUID, reason_code: str) -> PayrollPaymentReleaseReviewRecord:
        self._require(context, PayrollPermission.PAYMENT_RELEASE_APPROVE)
        value = await self._locked_release(session, context, release_id)
        if value.lifecycle != "draft" or value.review_state != "accepted":
            raise PayrollConflictError("reviewed payment release is required")
        value.lifecycle = "approved_for_release"
        record = await self._review(session, context, value, PaymentReleaseReviewDecision.APPROVED, reason_code)
        self._stage_release(session, context, value, EventType.PAYROLL_PAYMENT_RELEASE_APPROVED, "payroll.payment_release.approved")
        await session.commit()
        return record

    async def execution_handoff(self, session: AsyncSession, *, context: AuthorizationContext, release_id: UUID) -> PaymentExecutionHandoff:
        self._require(context, PayrollPermission.PAYMENT_RELEASE_READ)
        value = await session.scalar(select(PayrollPaymentReleaseRecord).where(PayrollPaymentReleaseRecord.company_id == context.company.id, PayrollPaymentReleaseRecord.id == release_id, PayrollPaymentReleaseRecord.lifecycle == "approved_for_release"))
        if value is None:
            raise PayrollConflictError("approved payment release is unavailable")
        instructions = tuple((await session.scalars(select(PayrollPaymentInstructionRecord).where(PayrollPaymentInstructionRecord.release_id == value.id, PayrollPaymentInstructionRecord.disposition == "ready").order_by(PayrollPaymentInstructionRecord.employee_id))).all())
        approval = await session.scalar(select(PayrollPaymentReleaseReviewRecord.review_digest).where(PayrollPaymentReleaseReviewRecord.release_id == value.id, PayrollPaymentReleaseReviewRecord.decision == "approved"))
        if approval is None:
            raise PayrollConflictError("payment release approval evidence is unavailable")
        identity = canonical_digest({"release_id": str(value.id), "package_digest": value.package_digest, "instruction_identities": tuple(item.instruction_identity for item in instructions)})
        return PaymentExecutionHandoff(PAYMENT_EXECUTION_HANDOFF_VERSION, value.company_id, value.pay_period_id, value.id, value.package_identity, value.package_digest, value.currency, tuple(item.instruction_identity for item in instructions), value.aggregate_release_amount, approval, f"payment-execution:{identity}")

    @staticmethod
    def _resolution(employee_id: UUID, state: DestinationAdmissionState, value: PayrollPaymentDestinationVersion | None = None) -> DestinationResolution:
        content = {"employee_id": str(employee_id), "state": state.value, "destination_id": str(value.id) if value else None, "destination_digest": value.authority_digest if value else None, "method": value.method_type if value else None, "protected_reference": value.destination_reference if value else None}
        return DestinationResolution(employee_id, state, value.id if value else None, value.authority_digest if value else None, PaymentMethod(value.method_type) if value else None, value.destination_reference if value else None, canonical_digest(content))

    async def _review(self, session: AsyncSession, context: AuthorizationContext, value: PayrollPaymentReleaseRecord, decision: PaymentReleaseReviewDecision, reason_code: str) -> PayrollPaymentReleaseReviewRecord:
        reason = reason_code.strip()
        if not reason or len(reason) > 80:
            raise PayrollConflictError("payment release review evidence is invalid")
        sequence = (await session.scalar(select(func.count(PayrollPaymentReleaseReviewRecord.id)).where(PayrollPaymentReleaseReviewRecord.release_id == value.id)) or 0) + 1
        at = datetime.now(timezone.utc)
        digest = canonical_digest({"release_id": str(value.id), "package_digest": value.package_digest, "sequence": sequence, "actor": str(context.user.id), "decision": decision.value, "reason": reason, "at": at.isoformat()})
        record = PayrollPaymentReleaseReviewRecord(company_id=value.company_id, release_id=value.id, review_sequence=sequence, actor_user_id=context.user.id, decision=decision.value, reason_code=reason, safe_note=None, package_digest=value.package_digest, review_digest=digest, reviewed_at=at)
        session.add(record)
        await session.flush()
        return record

    @staticmethod
    async def _locked_release(session: AsyncSession, context: AuthorizationContext, release_id: UUID) -> PayrollPaymentReleaseRecord:
        value = await session.scalar(select(PayrollPaymentReleaseRecord).where(PayrollPaymentReleaseRecord.company_id == context.company.id, PayrollPaymentReleaseRecord.id == release_id).with_for_update())
        if value is None:
            raise PayrollConflictError("payment release was not found")
        return value

    @staticmethod
    def _require(context: AuthorizationContext, permission: str) -> None:
        if not context.has_permission(permission):
            raise PayrollAuthorizationError("Payroll payment permission denied")

    def _stage_destination(self, session: AsyncSession, context: AuthorizationContext, value: PayrollPaymentDestinationVersion, event: EventType, action: str) -> None:
        details: dict[str, object] = {"destination_id": str(value.id), "authority_digest": value.authority_digest, "lifecycle": value.lifecycle}
        BusinessEventService.stage(session, BusinessEventCreate(event_type=event, entity_type="payroll_payment_destination", entity_id=value.id, company_id=value.company_id, user_id=context.user.id, payload=details))
        self._audit.stage(session, AuditEntry(action=action, resource_type="payroll_payment_destination", actor_user_id=context.user.id, company_id=value.company_id, resource_id=value.id, details=details))

    def _stage_release(self, session: AsyncSession, context: AuthorizationContext, value: PayrollPaymentReleaseRecord, event: EventType, action: str) -> None:
        details: dict[str, object] = {"release_id": str(value.id), "package_digest": value.package_digest, "pay_period_id": str(value.pay_period_id), "lifecycle": value.lifecycle}
        BusinessEventService.stage(session, BusinessEventCreate(event_type=event, entity_type="payroll_payment_release", entity_id=value.id, company_id=value.company_id, user_id=context.user.id, payload=details))
        self._audit.stage(session, AuditEntry(action=action, resource_type="payroll_payment_release", actor_user_id=context.user.id, company_id=value.company_id, resource_id=value.id, details=details))
