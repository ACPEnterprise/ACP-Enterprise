"""Provider-neutral Payroll payment execution evidence; never moves money itself."""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, AuditService, audit_service
from app.platform.permissions.authorization import AuthorizationContext

from .contracts import PayrollAuthorizationError, PayrollConflictError, canonical_digest
from .models import (
    PayrollPaymentExecutionEvidenceRecord,
    PayrollPaymentExecutionItemRecord,
    PayrollPaymentExecutionRecord,
    PayrollPaymentInstructionRecord,
    PayrollPaymentReleaseRecord,
)
from .permissions import PayrollPermission

PAYMENT_EXECUTION_VERSION = "payroll.payment-execution.v1"
SETTLEMENT_HANDOFF_VERSION = "payroll.payment-settlement-handoff.v1"


class ExecutionLifecycle(StrEnum):
    AUTHORIZED = "authorized"
    SUBMISSION_PENDING = "submission_pending"
    SUBMITTED = "submitted"
    PROVIDER_ACKNOWLEDGED = "provider_acknowledged"
    SETTLEMENT_PENDING = "settlement_pending"
    PARTIALLY_SETTLED = "partially_settled"
    SETTLED = "settled"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELED = "canceled"
    UNCERTAIN = "uncertain"


class InstructionExecutionState(StrEnum):
    AUTHORIZED = "authorized"
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    SETTLEMENT_PENDING = "settlement_pending"
    SETTLED = "settled"
    REJECTED = "rejected"
    FAILED = "failed"
    UNRESOLVED = "unresolved"


class ProviderResultState(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PENDING = "pending"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class ProviderInstruction:
    instruction_identity: str
    instruction_digest: str
    protected_destination_reference: str
    amount: Decimal
    currency: str


@dataclass(frozen=True)
class ProviderExecutionRequest:
    execution_identity: str
    idempotency_identity: str
    provider_identity: str
    provider_version: str
    instructions: tuple[ProviderInstruction, ...]
    request_digest: str


@dataclass(frozen=True)
class ProviderAcknowledgement:
    state: ProviderResultState
    provider_safe_reference: str
    acknowledged_at: datetime
    request_digest: str
    response_digest: str


class PaymentExecutionProvider(Protocol):
    identity: str
    version: str

    async def submit(self, request: ProviderExecutionRequest) -> ProviderAcknowledgement: ...


class SyntheticPaymentExecutionProvider:
    """Test-only, non-network provider; construction is prohibited outside tests."""

    identity = "synthetic.payment-provider"
    version = "test.v1"

    def __init__(self, *, environment: str, result: ProviderResultState = ProviderResultState.ACCEPTED) -> None:
        if environment != "test":
            raise PayrollConflictError("synthetic payment provider is test-only")
        self._result = result
        self.calls = 0
        self._responses: dict[str, ProviderAcknowledgement] = {}

    async def submit(self, request: ProviderExecutionRequest) -> ProviderAcknowledgement:
        prior = self._responses.get(request.idempotency_identity)
        if prior:
            return prior
        self.calls += 1
        reference = f"synthetic-provider:{request.request_digest[:16]}"
        response_digest = canonical_digest({"state": self._result.value, "reference": reference, "request_digest": request.request_digest})
        value = ProviderAcknowledgement(self._result, reference, datetime.now(timezone.utc), request.request_digest, response_digest)
        self._responses[request.idempotency_identity] = value
        return value


@dataclass(frozen=True)
class ExecutionCandidate:
    company_id: UUID
    release_id: UUID
    payroll_run_id: UUID
    package_digest: str
    provider_identity: str
    provider_version: str
    idempotency_identity: str
    currency: str
    instruction_ids: tuple[UUID, ...]
    instruction_digests: tuple[str, ...]
    authorized_total: Decimal
    execution_identity: str
    execution_digest: str

    def canonical_content(self) -> dict[str, object]:
        return {"company_id": str(self.company_id), "release_id": str(self.release_id), "payroll_run_id": str(self.payroll_run_id), "package_digest": self.package_digest, "provider_identity": self.provider_identity, "provider_version": self.provider_version, "idempotency_identity": self.idempotency_identity, "currency": self.currency, "instruction_ids": tuple(str(value) for value in self.instruction_ids), "instruction_digests": self.instruction_digests, "authorized_total": str(self.authorized_total), "definition_version": PAYMENT_EXECUTION_VERSION}

    def verify(self) -> None:
        digest = canonical_digest(self.canonical_content())
        if digest != self.execution_digest or self.execution_identity != f"payroll-payment-execution:{digest}":
            raise PayrollConflictError("payment execution candidate is invalid")


@dataclass(frozen=True)
class SettlementItemEvidence:
    instruction_id: UUID
    state: InstructionExecutionState
    provider_safe_reference: str
    evidence_digest: str


@dataclass(frozen=True)
class AccountingSettlementHandoff:
    definition_version: str
    company_id: UUID
    payroll_run_id: UUID
    release_id: UUID
    release_digest: str
    execution_id: UUID
    execution_digest: str
    settlement_evidence_digests: tuple[str, ...]
    settled_total: Decimal
    currency: str


class PayrollPaymentExecutionService:
    def __init__(self, *, audit: AuditService = audit_service) -> None:
        self._audit = audit

    async def create_candidate(self, session: AsyncSession, *, context: AuthorizationContext, release_id: UUID, provider_identity: str, provider_version: str, idempotency_identity: str) -> ExecutionCandidate:
        self._require(context, PayrollPermission.PAYMENT_EXECUTION_AUTHORIZE)
        release = await session.scalar(select(PayrollPaymentReleaseRecord).where(PayrollPaymentReleaseRecord.company_id == context.company.id, PayrollPaymentReleaseRecord.id == release_id, PayrollPaymentReleaseRecord.lifecycle == "approved_for_release"))
        if release is None:
            raise PayrollConflictError("approved-for-release payment package is required")
        instructions = tuple((await session.scalars(select(PayrollPaymentInstructionRecord).where(PayrollPaymentInstructionRecord.company_id == context.company.id, PayrollPaymentInstructionRecord.release_id == release.id, PayrollPaymentInstructionRecord.disposition == "ready").order_by(PayrollPaymentInstructionRecord.id))).all())
        if not instructions or any(not item.protected_destination_reference for item in instructions):
            raise PayrollConflictError("release-ready payment instructions are required")
        total = sum((item.amount for item in instructions), Decimal(0))
        if total != release.aggregate_release_amount:
            raise PayrollConflictError("payment instruction total does not match approved release")
        provisional = ExecutionCandidate(release.company_id, release.id, release.payroll_run_id, release.package_digest, provider_identity, provider_version, idempotency_identity, release.currency, tuple(item.id for item in instructions), tuple(item.instruction_digest for item in instructions), total, "", "")
        digest = canonical_digest(provisional.canonical_content())
        return ExecutionCandidate(**{**provisional.__dict__, "execution_identity": f"payroll-payment-execution:{digest}", "execution_digest": digest})

    async def authorize(self, session: AsyncSession, *, context: AuthorizationContext, candidate: ExecutionCandidate) -> PayrollPaymentExecutionRecord:
        self._require(context, PayrollPermission.PAYMENT_EXECUTION_AUTHORIZE)
        candidate.verify()
        if candidate.company_id != context.company.id:
            raise PayrollConflictError("payment execution Company scope mismatch")
        await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"payroll-payment-execution:{candidate.company_id}:{candidate.release_id}"})
        existing = await session.scalar(select(PayrollPaymentExecutionRecord).where(PayrollPaymentExecutionRecord.company_id == context.company.id, PayrollPaymentExecutionRecord.execution_digest == candidate.execution_digest))
        if existing:
            return existing
        active = await session.scalar(select(PayrollPaymentExecutionRecord).where(PayrollPaymentExecutionRecord.company_id == context.company.id, PayrollPaymentExecutionRecord.release_id == candidate.release_id, PayrollPaymentExecutionRecord.lifecycle.in_(("authorized", "submission_pending", "submitted", "provider_acknowledged", "settlement_pending", "partially_settled", "uncertain"))))
        if active:
            raise PayrollConflictError("active payment execution already exists")
        release = await session.scalar(select(PayrollPaymentReleaseRecord).where(PayrollPaymentReleaseRecord.company_id == context.company.id, PayrollPaymentReleaseRecord.id == candidate.release_id, PayrollPaymentReleaseRecord.package_digest == candidate.package_digest, PayrollPaymentReleaseRecord.lifecycle == "approved_for_release").with_for_update())
        if release is None:
            raise PayrollConflictError("approved payment release evidence changed")
        instructions = tuple((await session.scalars(select(PayrollPaymentInstructionRecord).where(PayrollPaymentInstructionRecord.release_id == release.id, PayrollPaymentInstructionRecord.id.in_(candidate.instruction_ids)).order_by(PayrollPaymentInstructionRecord.id))).all())
        if tuple(item.instruction_digest for item in instructions) != candidate.instruction_digests or sum((item.amount for item in instructions), Decimal(0)) != candidate.authorized_total:
            raise PayrollConflictError("payment instruction evidence changed")
        at = datetime.now(timezone.utc)
        value = PayrollPaymentExecutionRecord(company_id=candidate.company_id, release_id=candidate.release_id, payroll_run_id=candidate.payroll_run_id, package_digest=candidate.package_digest, definition_version=PAYMENT_EXECUTION_VERSION, provider_identity=candidate.provider_identity, provider_version=candidate.provider_version, execution_idempotency_key=candidate.idempotency_identity, execution_identity=candidate.execution_identity, execution_digest=candidate.execution_digest, currency=candidate.currency, authorized_total=candidate.authorized_total, lifecycle="authorized", authorized_by_user_id=context.user.id, authorized_at=at)
        session.add(value)
        await session.flush()
        for instruction in instructions:
            session.add(PayrollPaymentExecutionItemRecord(company_id=value.company_id, execution_id=value.id, instruction_id=instruction.id, instruction_digest=instruction.instruction_digest, amount=instruction.amount, currency=instruction.currency, lifecycle="authorized"))
        release.execution_started_at = at
        self._stage(session, context, value, EventType.PAYROLL_PAYMENT_EXECUTION_AUTHORIZED, "payroll.payment_execution.authorized")
        await session.commit()
        return value

    async def submit(self, session: AsyncSession, *, context: AuthorizationContext, execution_id: UUID, provider: PaymentExecutionProvider) -> PayrollPaymentExecutionRecord:
        self._require(context, PayrollPermission.PAYMENT_EXECUTION_AUTHORIZE)
        value = await self._locked(session, context, execution_id)
        if provider.identity != value.provider_identity or provider.version != value.provider_version:
            raise PayrollConflictError("payment provider identity mismatch")
        if value.lifecycle not in {"authorized", "submission_pending"}:
            if value.lifecycle in {"submitted", "provider_acknowledged", "settlement_pending", "partially_settled", "settled", "rejected"}:
                return value
            raise PayrollConflictError("payment execution is not safely submit-ready")
        items = tuple((await session.scalars(select(PayrollPaymentExecutionItemRecord).where(PayrollPaymentExecutionItemRecord.execution_id == value.id).order_by(PayrollPaymentExecutionItemRecord.instruction_id))).all())
        source = tuple((await session.scalars(select(PayrollPaymentInstructionRecord).where(PayrollPaymentInstructionRecord.id.in_(tuple(item.instruction_id for item in items))).order_by(PayrollPaymentInstructionRecord.id))).all())
        request_items = tuple(ProviderInstruction(item.instruction_identity, item.instruction_digest, item.protected_destination_reference or "", item.amount, item.currency) for item in source)
        request_digest = canonical_digest({"execution_identity": value.execution_identity, "instructions": tuple((item.instruction_identity, item.instruction_digest, str(item.amount), item.currency, item.protected_destination_reference) for item in request_items)})
        request = ProviderExecutionRequest(value.execution_identity, value.execution_idempotency_key, value.provider_identity, value.provider_version, request_items, request_digest)
        value.lifecycle = "submission_pending"
        await session.flush()
        acknowledgement = await provider.submit(request)
        return await self.record_acknowledgement(session, context=context, execution_id=value.id, acknowledgement=acknowledgement)

    async def record_acknowledgement(self, session: AsyncSession, *, context: AuthorizationContext, execution_id: UUID, acknowledgement: ProviderAcknowledgement) -> PayrollPaymentExecutionRecord:
        self._require(context, PayrollPermission.PAYMENT_EXECUTION_AUTHORIZE)
        value = await self._locked(session, context, execution_id)
        existing = await session.scalar(select(PayrollPaymentExecutionEvidenceRecord).where(PayrollPaymentExecutionEvidenceRecord.execution_id == value.id, PayrollPaymentExecutionEvidenceRecord.response_digest == acknowledgement.response_digest))
        if existing:
            return value
        if value.request_digest and value.request_digest != acknowledgement.request_digest:
            raise PayrollConflictError("contradictory provider acknowledgement")
        if value.response_digest and value.response_digest != acknowledgement.response_digest:
            raise PayrollConflictError("contradictory provider acknowledgement")
        lifecycle = {ProviderResultState.ACCEPTED: "provider_acknowledged", ProviderResultState.PENDING: "submitted", ProviderResultState.REJECTED: "rejected", ProviderResultState.UNCERTAIN: "uncertain"}[acknowledgement.state]
        value.lifecycle, value.provider_reference, value.request_digest, value.response_digest = lifecycle, acknowledgement.provider_safe_reference, acknowledgement.request_digest, acknowledgement.response_digest
        evidence = self._evidence(session, context, value, "uncertain" if acknowledgement.state is ProviderResultState.UNCERTAIN else "acknowledgement", acknowledgement.provider_safe_reference, acknowledgement.request_digest, acknowledgement.response_digest, acknowledgement.acknowledged_at)
        items = tuple((await session.scalars(select(PayrollPaymentExecutionItemRecord).where(PayrollPaymentExecutionItemRecord.execution_id == value.id))).all())
        item_state = "unresolved" if acknowledgement.state is ProviderResultState.UNCERTAIN else "rejected" if acknowledgement.state is ProviderResultState.REJECTED else "acknowledged"
        for item in items:
            item.lifecycle, item.provider_safe_reference, item.evidence_digest = item_state, acknowledgement.provider_safe_reference, evidence.evidence_digest
        event = EventType.PAYROLL_PAYMENT_EXECUTION_FAILED if acknowledgement.state in {ProviderResultState.REJECTED, ProviderResultState.UNCERTAIN} else EventType.PAYROLL_PAYMENT_EXECUTION_ACKNOWLEDGED
        self._stage(session, context, value, event, f"payroll.payment_execution.{lifecycle}")
        await session.commit()
        return value

    async def record_settlement(self, session: AsyncSession, *, context: AuthorizationContext, execution_id: UUID, outcomes: tuple[SettlementItemEvidence, ...], occurred_at: datetime) -> PayrollPaymentExecutionRecord:
        self._require(context, PayrollPermission.PAYMENT_SETTLEMENT_RECONCILE)
        value = await self._locked(session, context, execution_id)
        if value.lifecycle not in {"provider_acknowledged", "settlement_pending", "partially_settled"}:
            raise PayrollConflictError("acknowledged execution is required for settlement")
        items = tuple((await session.scalars(select(PayrollPaymentExecutionItemRecord).where(PayrollPaymentExecutionItemRecord.execution_id == value.id).order_by(PayrollPaymentExecutionItemRecord.instruction_id))).all())
        if {item.instruction_id for item in items} != {item.instruction_id for item in outcomes}:
            raise PayrollConflictError("settlement evidence population is incomplete")
        by_id = {item.instruction_id: item for item in outcomes}
        allowed = {InstructionExecutionState.SETTLED, InstructionExecutionState.FAILED, InstructionExecutionState.REJECTED, InstructionExecutionState.UNRESOLVED, InstructionExecutionState.SETTLEMENT_PENDING}
        if any(item.state not in allowed for item in outcomes):
            raise PayrollConflictError("settlement outcome is invalid")
        for item in items:
            outcome = by_id[item.instruction_id]
            expected = canonical_digest({"instruction_id": str(outcome.instruction_id), "state": outcome.state.value, "provider_safe_reference": outcome.provider_safe_reference})
            if expected != outcome.evidence_digest:
                raise PayrollConflictError("settlement evidence digest is invalid")
            item.lifecycle, item.provider_safe_reference, item.evidence_digest = outcome.state.value, outcome.provider_safe_reference, outcome.evidence_digest
        states = {item.state for item in outcomes}
        if states == {InstructionExecutionState.SETTLED}:
            value.lifecycle = "settled"
        elif InstructionExecutionState.SETTLED in states:
            value.lifecycle = "partially_settled"
        elif states <= {InstructionExecutionState.FAILED, InstructionExecutionState.REJECTED}:
            value.lifecycle = "failed"
        else:
            value.lifecycle = "settlement_pending"
        response_digest = canonical_digest(tuple(sorted(item.evidence_digest for item in outcomes)))
        self._evidence(session, context, value, "settlement" if value.lifecycle in {"settled", "partially_settled", "settlement_pending"} else "failure", value.provider_reference, value.request_digest or canonical_digest({}), response_digest, occurred_at)
        self._stage(session, context, value, EventType.PAYROLL_PAYMENT_SETTLEMENT_RECORDED if value.lifecycle != "failed" else EventType.PAYROLL_PAYMENT_EXECUTION_FAILED, f"payroll.payment_execution.{value.lifecycle}")
        await session.commit()
        return value

    async def accounting_handoff(self, session: AsyncSession, *, context: AuthorizationContext, execution_id: UUID) -> AccountingSettlementHandoff:
        self._require(context, PayrollPermission.PAYMENT_EXECUTION_READ)
        value = await session.scalar(select(PayrollPaymentExecutionRecord).where(PayrollPaymentExecutionRecord.company_id == context.company.id, PayrollPaymentExecutionRecord.id == execution_id, PayrollPaymentExecutionRecord.lifecycle.in_(("settled", "partially_settled"))))
        if value is None:
            raise PayrollConflictError("settlement evidence is unavailable")
        items = tuple((await session.scalars(select(PayrollPaymentExecutionItemRecord).where(PayrollPaymentExecutionItemRecord.execution_id == value.id, PayrollPaymentExecutionItemRecord.lifecycle == "settled"))).all())
        evidence = tuple((await session.scalars(select(PayrollPaymentExecutionEvidenceRecord).where(PayrollPaymentExecutionEvidenceRecord.execution_id == value.id, PayrollPaymentExecutionEvidenceRecord.evidence_type == "settlement").order_by(PayrollPaymentExecutionEvidenceRecord.occurred_at))).all())
        return AccountingSettlementHandoff(SETTLEMENT_HANDOFF_VERSION, value.company_id, value.payroll_run_id, value.release_id, value.package_digest, value.id, value.execution_digest, tuple(item.evidence_digest for item in evidence), sum((item.amount for item in items), Decimal(0)), value.currency)

    def _evidence(self, session: AsyncSession, context: AuthorizationContext, value: PayrollPaymentExecutionRecord, evidence_type: str, provider_reference: str | None, request_digest: str, response_digest: str, occurred_at: datetime) -> PayrollPaymentExecutionEvidenceRecord:
        digest = canonical_digest({"execution_id": str(value.id), "type": evidence_type, "provider": value.provider_identity, "provider_version": value.provider_version, "provider_reference": provider_reference, "request_digest": request_digest, "response_digest": response_digest, "occurred_at": occurred_at.isoformat()})
        record = PayrollPaymentExecutionEvidenceRecord(company_id=value.company_id, execution_id=value.id, evidence_type=evidence_type, provider_identity=value.provider_identity, provider_version=value.provider_version, provider_safe_reference=provider_reference, request_digest=request_digest, response_digest=response_digest, evidence_digest=digest, recorded_by_user_id=context.user.id, occurred_at=occurred_at)
        session.add(record)
        return record

    @staticmethod
    async def _locked(session: AsyncSession, context: AuthorizationContext, execution_id: UUID) -> PayrollPaymentExecutionRecord:
        value = await session.scalar(select(PayrollPaymentExecutionRecord).where(PayrollPaymentExecutionRecord.company_id == context.company.id, PayrollPaymentExecutionRecord.id == execution_id).with_for_update())
        if value is None:
            raise PayrollConflictError("payment execution was not found")
        return value

    @staticmethod
    def _require(context: AuthorizationContext, permission: str) -> None:
        if not context.has_permission(permission):
            raise PayrollAuthorizationError("Payroll payment execution permission denied")

    def _stage(self, session: AsyncSession, context: AuthorizationContext, value: PayrollPaymentExecutionRecord, event: EventType, action: str) -> None:
        details: dict[str, object] = {"execution_id": str(value.id), "release_id": str(value.release_id), "provider_identity": value.provider_identity, "provider_version": value.provider_version, "lifecycle": value.lifecycle, "execution_digest": value.execution_digest}
        BusinessEventService.stage(session, BusinessEventCreate(event_type=event, entity_type="payroll_payment_execution", entity_id=value.id, company_id=value.company_id, user_id=context.user.id, payload=details))
        self._audit.stage(session, AuditEntry(action=action, resource_type="payroll_payment_execution", actor_user_id=context.user.id, company_id=value.company_id, resource_id=value.id, details=details))
