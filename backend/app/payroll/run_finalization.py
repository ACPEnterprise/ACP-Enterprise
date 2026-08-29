"""Company/pay-period Payroll-run assembly and final approval authority.

An approved run is Payroll evidence only. It is neither payment authorization nor
Accounting posting or tax-filing authority.
"""

from dataclasses import dataclass, replace
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
from app.timekeeping.models import PayPeriod

from .contracts import PayrollAuthorizationError, PayrollConflictError, canonical_digest
from .models import (
    PayrollGrossCalculationResultRecord,
    PayrollRunMemberRecord,
    PayrollRunRecord,
    PayrollRunReviewRecord,
    PayrollTaxDeductionResultRecord,
)
from .permissions import PayrollPermission
from .tax_authority import TaxDeductionAdmissionResult, TaxDeductionAdmissionState

PAYROLL_RUN_ASSEMBLY_VERSION = "payroll.run-assembly.v1"
PAYROLL_RUN_HANDOFF_VERSION = "payroll.run-approved-handoff.v1"


class PayrollRunDisposition(StrEnum):
    READY = "ready"
    BLOCKED = "blocked"
    EXCLUDED = "excluded"
    NOT_APPLICABLE = "not_applicable"


class PayrollRunLifecycle(StrEnum):
    ASSEMBLED = "assembled"
    UNDER_REVIEW = "under_review"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    VOIDED = "voided"


class PayrollRunReviewState(StrEnum):
    NOT_STARTED = "not_started"
    UNDER_REVIEW = "under_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class PayrollRunReviewDecision(StrEnum):
    INITIATED = "initiated"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    APPROVED = "approved"


@dataclass(frozen=True)
class PayrollPopulationEvidence:
    company_id: UUID
    pay_period_id: UUID
    population_identity: str
    definition_version: str
    employee_ids: tuple[UUID, ...]
    evidence_digest: str

    def canonical_content(self) -> dict[str, object]:
        return {
            "company_id": str(self.company_id),
            "pay_period_id": str(self.pay_period_id),
            "population_identity": self.population_identity,
            "definition_version": self.definition_version,
            "employee_ids": tuple(sorted(str(item) for item in self.employee_ids)),
        }

    def verify(self) -> None:
        if len(set(self.employee_ids)) != len(self.employee_ids):
            raise PayrollConflictError("Payroll population contains duplicate Employees")
        if canonical_digest(self.canonical_content()) != self.evidence_digest:
            raise PayrollConflictError("Payroll population evidence digest is invalid")


@dataclass(frozen=True)
class PayrollRunMemberInput:
    employee_id: UUID
    disposition: PayrollRunDisposition
    tax_result_id: UUID | None = None
    blocked_admission: TaxDeductionAdmissionResult | None = None
    disposition_authority_digest: str | None = None


@dataclass(frozen=True)
class PayrollRunMember:
    employee_id: UUID
    disposition: PayrollRunDisposition
    gross_result_id: UUID | None
    gross_result_digest: str | None
    tax_result_id: UUID | None
    tax_result_digest: str | None
    blocker_evidence_digest: str | None
    disposition_authority_digest: str | None
    gross: Decimal
    employee_taxes: Decimal
    employee_deductions: Decimal
    net_pay: Decimal
    employer_contributions: Decimal
    membership_digest: str

    def canonical_content(self) -> dict[str, object]:
        return {
            "employee_id": str(self.employee_id),
            "disposition": self.disposition.value,
            "gross_result_id": str(self.gross_result_id) if self.gross_result_id else None,
            "gross_result_digest": self.gross_result_digest,
            "tax_result_id": str(self.tax_result_id) if self.tax_result_id else None,
            "tax_result_digest": self.tax_result_digest,
            "blocker_evidence_digest": self.blocker_evidence_digest,
            "disposition_authority_digest": self.disposition_authority_digest,
            "gross": str(self.gross),
            "employee_taxes": str(self.employee_taxes),
            "employee_deductions": str(self.employee_deductions),
            "net_pay": str(self.net_pay),
            "employer_contributions": str(self.employer_contributions),
        }


@dataclass(frozen=True)
class PayrollRunCandidate:
    company_id: UUID
    pay_period_id: UUID
    schedule_definition_id: str
    schedule_version: str
    assembly_version: str
    population_identity: str
    population_digest: str
    currency: str
    members: tuple[PayrollRunMember, ...]
    aggregate_gross: Decimal
    aggregate_employee_taxes: Decimal
    aggregate_employee_deductions: Decimal
    aggregate_net_pay: Decimal
    aggregate_employer_contributions: Decimal
    run_identity: str
    run_digest: str
    assembled_at: datetime
    supersedes_run_identity: str | None = None

    def canonical_economic_content(self) -> dict[str, object]:
        return {
            "company_id": str(self.company_id),
            "pay_period_id": str(self.pay_period_id),
            "schedule_definition_id": self.schedule_definition_id,
            "schedule_version": self.schedule_version,
            "assembly_version": self.assembly_version,
            "population_identity": self.population_identity,
            "population_digest": self.population_digest,
            "currency": self.currency,
            "members": tuple(item.canonical_content() for item in self.members),
            "aggregate_gross": str(self.aggregate_gross),
            "aggregate_employee_taxes": str(self.aggregate_employee_taxes),
            "aggregate_employee_deductions": str(self.aggregate_employee_deductions),
            "aggregate_net_pay": str(self.aggregate_net_pay),
            "aggregate_employer_contributions": str(self.aggregate_employer_contributions),
            "supersedes_run_identity": self.supersedes_run_identity,
        }

    def verify(self) -> None:
        digest = canonical_digest(self.canonical_economic_content())
        if self.run_digest != digest or self.run_identity != f"payroll-run:{digest}":
            raise PayrollConflictError("Payroll run identity or digest is invalid")
        if len({item.employee_id for item in self.members}) != len(self.members):
            raise PayrollConflictError("Payroll run contains duplicate Employees")
        for item in self.members:
            if canonical_digest(item.canonical_content()) != item.membership_digest:
                raise PayrollConflictError("Payroll run membership digest is invalid")
        ready = tuple(item for item in self.members if item.disposition is PayrollRunDisposition.READY)
        totals = (
            sum((item.gross for item in ready), Decimal(0)),
            sum((item.employee_taxes for item in ready), Decimal(0)),
            sum((item.employee_deductions for item in ready), Decimal(0)),
            sum((item.net_pay for item in ready), Decimal(0)),
            sum((item.employer_contributions for item in ready), Decimal(0)),
        )
        if totals != (
            self.aggregate_gross,
            self.aggregate_employee_taxes,
            self.aggregate_employee_deductions,
            self.aggregate_net_pay,
            self.aggregate_employer_contributions,
        ):
            raise PayrollConflictError("Payroll run aggregate reconciliation failed")


@dataclass(frozen=True)
class ApprovedPayrollRunHandoff:
    definition_version: str
    company_id: UUID
    pay_period_id: UUID
    run_id: UUID
    run_identity: str
    run_digest: str
    currency: str
    aggregate_gross: Decimal
    aggregate_employee_taxes: Decimal
    aggregate_employee_deductions: Decimal
    aggregate_net_pay: Decimal
    aggregate_employer_contributions: Decimal
    approval_evidence_digest: str
    purpose: str


class PayrollRunService:
    def __init__(self, *, audit: AuditService = audit_service) -> None:
        self._audit = audit

    async def assemble_candidate(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        population: PayrollPopulationEvidence,
        member_inputs: tuple[PayrollRunMemberInput, ...],
        currency: str,
        assembled_at: datetime,
        supersedes_run_identity: str | None = None,
    ) -> PayrollRunCandidate:
        self._require(context, PayrollPermission.RUN_ASSEMBLE)
        population.verify()
        if population.company_id != context.company.id:
            raise PayrollConflictError("Payroll population Company scope mismatch")
        if set(population.employee_ids) != {item.employee_id for item in member_inputs}:
            raise PayrollConflictError("Payroll run population is incomplete")
        if len(member_inputs) != len(population.employee_ids):
            raise PayrollConflictError("Payroll run membership is ambiguous")
        period = await session.scalar(
            select(PayPeriod).where(
                PayPeriod.id == population.pay_period_id,
                PayPeriod.company_id == context.company.id,
            )
        )
        if period is None:
            raise PayrollConflictError("Payroll pay period is unavailable")
        members = tuple(
            [
                await self._resolve_member(
                    session,
                    company_id=context.company.id,
                    pay_period_id=population.pay_period_id,
                    currency=currency,
                    value=item,
                )
                for item in sorted(member_inputs, key=lambda item: str(item.employee_id))
            ]
        )
        ready = tuple(item for item in members if item.disposition is PayrollRunDisposition.READY)
        provisional = PayrollRunCandidate(
            company_id=context.company.id,
            pay_period_id=population.pay_period_id,
            schedule_definition_id=period.schedule_definition_id,
            schedule_version=str(period.schedule_version),
            assembly_version=PAYROLL_RUN_ASSEMBLY_VERSION,
            population_identity=population.population_identity,
            population_digest=population.evidence_digest,
            currency=currency,
            members=members,
            aggregate_gross=sum((item.gross for item in ready), Decimal(0)),
            aggregate_employee_taxes=sum((item.employee_taxes for item in ready), Decimal(0)),
            aggregate_employee_deductions=sum((item.employee_deductions for item in ready), Decimal(0)),
            aggregate_net_pay=sum((item.net_pay for item in ready), Decimal(0)),
            aggregate_employer_contributions=sum((item.employer_contributions for item in ready), Decimal(0)),
            run_identity="",
            run_digest="",
            assembled_at=assembled_at,
            supersedes_run_identity=supersedes_run_identity,
        )
        digest = canonical_digest(provisional.canonical_economic_content())
        value = replace(provisional, run_identity=f"payroll-run:{digest}", run_digest=digest)
        value.verify()
        return value

    async def persist_candidate(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        candidate: PayrollRunCandidate,
    ) -> PayrollRunRecord:
        self._require(context, PayrollPermission.RUN_ASSEMBLE)
        candidate.verify()
        if candidate.company_id != context.company.id:
            raise PayrollConflictError("Payroll run Company scope mismatch")
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"payroll-run:{candidate.company_id}:{candidate.pay_period_id}"},
        )
        existing = await session.scalar(
            select(PayrollRunRecord).where(
                PayrollRunRecord.company_id == context.company.id,
                PayrollRunRecord.run_digest == candidate.run_digest,
            )
        )
        if existing is not None:
            if existing.run_identity != candidate.run_identity:
                raise PayrollConflictError("Payroll run persistence identity conflict")
            await self._verify_persisted(session, existing)
            return existing
        active = await session.scalar(
            select(PayrollRunRecord)
            .where(
                PayrollRunRecord.company_id == context.company.id,
                PayrollRunRecord.pay_period_id == candidate.pay_period_id,
                PayrollRunRecord.lifecycle.in_(("assembled", "under_review", "reviewed", "approved")),
            )
            .with_for_update()
        )
        prior = None
        if candidate.supersedes_run_identity:
            prior = await session.scalar(
                select(PayrollRunRecord)
                .where(
                    PayrollRunRecord.company_id == context.company.id,
                    PayrollRunRecord.run_identity == candidate.supersedes_run_identity,
                )
                .with_for_update()
            )
            if prior is None or active is None or prior.id != active.id or prior.consumed_by_payment_at is not None:
                raise PayrollConflictError("Payroll run supersession lineage conflict")
            prior.lifecycle = PayrollRunLifecycle.SUPERSEDED.value
            await session.flush()
        elif active is not None:
            raise PayrollConflictError("active Payroll run already exists")
        value = PayrollRunRecord(
            company_id=candidate.company_id,
            pay_period_id=candidate.pay_period_id,
            schedule_definition_id=candidate.schedule_definition_id,
            schedule_version=candidate.schedule_version,
            assembly_version=candidate.assembly_version,
            population_identity=candidate.population_identity,
            population_digest=candidate.population_digest,
            currency=candidate.currency,
            run_identity=candidate.run_identity,
            run_digest=candidate.run_digest,
            aggregate_gross=candidate.aggregate_gross,
            aggregate_employee_taxes=candidate.aggregate_employee_taxes,
            aggregate_employee_deductions=candidate.aggregate_employee_deductions,
            aggregate_net_pay=candidate.aggregate_net_pay,
            aggregate_employer_contributions=candidate.aggregate_employer_contributions,
            assembled_by_user_id=context.user.id,
            assembled_at=candidate.assembled_at,
            lifecycle=PayrollRunLifecycle.ASSEMBLED.value,
            review_state=PayrollRunReviewState.NOT_STARTED.value,
            supersedes_run_id=prior.id if prior else None,
        )
        session.add(value)
        await session.flush()
        for member in candidate.members:
            session.add(
                PayrollRunMemberRecord(
                    company_id=value.company_id,
                    run_id=value.id,
                    employee_id=member.employee_id,
                    disposition=member.disposition.value,
                    gross_result_id=member.gross_result_id,
                    gross_result_digest=member.gross_result_digest,
                    tax_result_id=member.tax_result_id,
                    tax_result_digest=member.tax_result_digest,
                    blocker_evidence_digest=member.blocker_evidence_digest,
                    disposition_authority_digest=member.disposition_authority_digest,
                    membership_digest=member.membership_digest,
                )
            )
        await session.flush()
        if prior:
            self._stage(session, context, prior, EventType.PAYROLL_RUN_SUPERSEDED, "payroll.run.superseded")
        self._stage(session, context, value, EventType.PAYROLL_RUN_ASSEMBLED, "payroll.run.assembled")
        await session.commit()
        return value

    async def initiate_review(self, session: AsyncSession, *, context: AuthorizationContext, run_id: UUID, reason_code: str, safe_note: str | None = None) -> PayrollRunReviewRecord:
        self._require(context, PayrollPermission.RUN_REVIEW)
        value = await self._locked_run(session, context, run_id)
        if value.lifecycle not in {PayrollRunLifecycle.ASSEMBLED.value, PayrollRunLifecycle.REJECTED.value}:
            raise PayrollConflictError("Payroll run cannot enter review")
        value.lifecycle = PayrollRunLifecycle.UNDER_REVIEW.value
        value.review_state = PayrollRunReviewState.UNDER_REVIEW.value
        evidence = await self._review(session, context, value, PayrollRunReviewDecision.INITIATED, reason_code, safe_note)
        self._stage(session, context, value, EventType.PAYROLL_RUN_REVIEW_INITIATED, "payroll.run.review_initiated")
        await session.commit()
        return evidence

    async def decide_review(self, session: AsyncSession, *, context: AuthorizationContext, run_id: UUID, decision: PayrollRunReviewDecision, reason_code: str, safe_note: str | None = None) -> PayrollRunReviewRecord:
        self._require(context, PayrollPermission.RUN_REVIEW)
        if decision not in {PayrollRunReviewDecision.ACCEPTED, PayrollRunReviewDecision.REJECTED}:
            raise PayrollConflictError("Payroll run review decision is invalid")
        value = await self._locked_run(session, context, run_id)
        if value.lifecycle != PayrollRunLifecycle.UNDER_REVIEW.value:
            raise PayrollConflictError("Payroll run is not under review")
        accepted = decision is PayrollRunReviewDecision.ACCEPTED
        value.lifecycle = PayrollRunLifecycle.REVIEWED.value if accepted else PayrollRunLifecycle.REJECTED.value
        value.review_state = PayrollRunReviewState.ACCEPTED.value if accepted else PayrollRunReviewState.REJECTED.value
        evidence = await self._review(session, context, value, decision, reason_code, safe_note)
        event = EventType.PAYROLL_RUN_REVIEW_ACCEPTED if accepted else EventType.PAYROLL_RUN_REVIEW_REJECTED
        self._stage(session, context, value, event, f"payroll.run.review_{decision.value}")
        await session.commit()
        return evidence

    async def approve(self, session: AsyncSession, *, context: AuthorizationContext, run_id: UUID, reason_code: str, safe_note: str | None = None) -> PayrollRunReviewRecord:
        self._require(context, PayrollPermission.RUN_APPROVE)
        value = await self._locked_run(session, context, run_id)
        if value.lifecycle != PayrollRunLifecycle.REVIEWED.value:
            raise PayrollConflictError("reviewed Payroll run is required for approval")
        value.lifecycle = PayrollRunLifecycle.APPROVED.value
        evidence = await self._review(session, context, value, PayrollRunReviewDecision.APPROVED, reason_code, safe_note)
        self._stage(session, context, value, EventType.PAYROLL_RUN_APPROVED, "payroll.run.approved")
        await session.commit()
        return evidence

    async def run(self, session: AsyncSession, *, context: AuthorizationContext, run_id: UUID) -> PayrollRunRecord:
        self._require(context, PayrollPermission.RUN_READ)
        value = await session.scalar(select(PayrollRunRecord).where(PayrollRunRecord.company_id == context.company.id, PayrollRunRecord.id == run_id))
        if value is None:
            raise PayrollConflictError("Payroll run was not found")
        await self._verify_persisted(session, value)
        return value

    async def approved_handoff(self, session: AsyncSession, *, context: AuthorizationContext, run_id: UUID, purpose: str) -> ApprovedPayrollRunHandoff:
        self._require(context, PayrollPermission.RUN_READ)
        value = await self.run(session, context=context, run_id=run_id)
        if value.lifecycle != PayrollRunLifecycle.APPROVED.value or purpose not in {"future_payment_release", "future_accounting_posting"}:
            raise PayrollConflictError("approved Payroll run handoff is unavailable")
        review_digest = await session.scalar(select(PayrollRunReviewRecord.review_digest).where(PayrollRunReviewRecord.run_id == run_id, PayrollRunReviewRecord.decision == "approved"))
        if review_digest is None:
            raise PayrollConflictError("Payroll run approval evidence is unavailable")
        return ApprovedPayrollRunHandoff(PAYROLL_RUN_HANDOFF_VERSION, value.company_id, value.pay_period_id, value.id, value.run_identity, value.run_digest, value.currency, value.aggregate_gross, value.aggregate_employee_taxes, value.aggregate_employee_deductions, value.aggregate_net_pay, value.aggregate_employer_contributions, review_digest, purpose)

    async def _resolve_member(self, session: AsyncSession, *, company_id: UUID, pay_period_id: UUID, currency: str, value: PayrollRunMemberInput) -> PayrollRunMember:
        zero = Decimal("0.00")
        fields: tuple[
            UUID | None,
            str | None,
            UUID | None,
            str | None,
            str | None,
            str | None,
            Decimal,
            Decimal,
            Decimal,
            Decimal,
            Decimal,
        ]
        if value.disposition is PayrollRunDisposition.READY:
            if value.tax_result_id is None or value.blocked_admission or value.disposition_authority_digest:
                raise PayrollConflictError("ready Payroll membership shape is invalid")
            tax = await session.scalar(select(PayrollTaxDeductionResultRecord).where(PayrollTaxDeductionResultRecord.company_id == company_id, PayrollTaxDeductionResultRecord.employee_id == value.employee_id, PayrollTaxDeductionResultRecord.pay_period_id == pay_period_id, PayrollTaxDeductionResultRecord.id == value.tax_result_id, PayrollTaxDeductionResultRecord.lifecycle == "approved", PayrollTaxDeductionResultRecord.currency == currency))
            if tax is None:
                raise PayrollConflictError("approved Employee tax result is unavailable")
            gross = await session.scalar(select(PayrollGrossCalculationResultRecord).where(PayrollGrossCalculationResultRecord.company_id == company_id, PayrollGrossCalculationResultRecord.employee_id == value.employee_id, PayrollGrossCalculationResultRecord.pay_period_id == pay_period_id, PayrollGrossCalculationResultRecord.id == tax.gross_result_id, PayrollGrossCalculationResultRecord.lifecycle == "approved", PayrollGrossCalculationResultRecord.calculation_digest == tax.gross_calculation_digest, PayrollGrossCalculationResultRecord.currency == currency))
            if gross is None:
                raise PayrollConflictError("Employee gross/net-pay lineage is invalid")
            fields = (gross.id, gross.calculation_digest, tax.id, tax.calculation_digest, None, None, tax.gross_pay, tax.employee_tax_total, tax.employee_deduction_total, tax.net_pay_candidate, tax.employer_contribution_total)
        elif value.disposition is PayrollRunDisposition.BLOCKED:
            admission = value.blocked_admission
            if admission is None or value.tax_result_id or value.disposition_authority_digest:
                raise PayrollConflictError("blocked Payroll membership shape is invalid")
            admission.verify()
            if admission.company_id != company_id or admission.employee_id != value.employee_id or admission.state not in {TaxDeductionAdmissionState.MISSING, TaxDeductionAdmissionState.EXPIRED, TaxDeductionAdmissionState.UNAPPROVED, TaxDeductionAdmissionState.CONFLICTING}:
                raise PayrollConflictError("blocked Payroll membership evidence is invalid")
            fields = (None, admission.gross_calculation_digest, None, None, admission.admission_digest, None, zero, zero, zero, zero, zero)
        else:
            if value.tax_result_id or value.blocked_admission or not value.disposition_authority_digest:
                raise PayrollConflictError("excluded Payroll membership requires authority evidence")
            fields = (None, None, None, None, None, value.disposition_authority_digest, zero, zero, zero, zero, zero)
        provisional = PayrollRunMember(
            employee_id=value.employee_id,
            disposition=value.disposition,
            gross_result_id=fields[0],
            gross_result_digest=fields[1],
            tax_result_id=fields[2],
            tax_result_digest=fields[3],
            blocker_evidence_digest=fields[4],
            disposition_authority_digest=fields[5],
            gross=fields[6],
            employee_taxes=fields[7],
            employee_deductions=fields[8],
            net_pay=fields[9],
            employer_contributions=fields[10],
            membership_digest="",
        )
        return replace(provisional, membership_digest=canonical_digest(provisional.canonical_content()))

    async def _review(self, session: AsyncSession, context: AuthorizationContext, value: PayrollRunRecord, decision: PayrollRunReviewDecision, reason_code: str, safe_note: str | None) -> PayrollRunReviewRecord:
        reason, note = reason_code.strip(), safe_note.strip() if safe_note else None
        if not reason or len(reason) > 80 or (note and (len(note) > 500 or "$" in note)):
            raise PayrollConflictError("Payroll run review evidence is unsafe")
        sequence = (await session.scalar(select(func.count(PayrollRunReviewRecord.id)).where(PayrollRunReviewRecord.run_id == value.id)) or 0) + 1
        at = datetime.now(timezone.utc)
        digest = canonical_digest({"run_id": str(value.id), "run_digest": value.run_digest, "sequence": sequence, "actor": str(context.user.id), "decision": decision.value, "reason_code": reason, "safe_note": note, "reviewed_at": at.isoformat()})
        record = PayrollRunReviewRecord(company_id=value.company_id, run_id=value.id, review_sequence=sequence, actor_user_id=context.user.id, decision=decision.value, reason_code=reason, safe_note=note, run_digest=value.run_digest, review_digest=digest, reviewed_at=at)
        session.add(record)
        await session.flush()
        return record

    async def _verify_persisted(
        self, session: AsyncSession, value: PayrollRunRecord
    ) -> None:
        records = tuple(
            (
                await session.scalars(
                    select(PayrollRunMemberRecord)
                    .where(PayrollRunMemberRecord.run_id == value.id)
                    .order_by(PayrollRunMemberRecord.employee_id)
                )
            ).all()
        )
        members: list[PayrollRunMember] = []
        for record in records:
            zero = Decimal("0.00")
            gross = taxes = deductions = net = employer = zero
            if record.disposition == PayrollRunDisposition.READY.value:
                if record.tax_result_id is None:
                    raise PayrollConflictError("persisted ready Payroll member is invalid")
                tax = await session.scalar(
                    select(PayrollTaxDeductionResultRecord).where(
                        PayrollTaxDeductionResultRecord.company_id == value.company_id,
                        PayrollTaxDeductionResultRecord.id == record.tax_result_id,
                        PayrollTaxDeductionResultRecord.calculation_digest
                        == record.tax_result_digest,
                    )
                )
                if tax is None:
                    raise PayrollConflictError("persisted Payroll member evidence changed")
                gross, taxes, deductions, net, employer = (
                    tax.gross_pay,
                    tax.employee_tax_total,
                    tax.employee_deduction_total,
                    tax.net_pay_candidate,
                    tax.employer_contribution_total,
                )
            member = PayrollRunMember(
                employee_id=record.employee_id,
                disposition=PayrollRunDisposition(record.disposition),
                gross_result_id=record.gross_result_id,
                gross_result_digest=record.gross_result_digest,
                tax_result_id=record.tax_result_id,
                tax_result_digest=record.tax_result_digest,
                blocker_evidence_digest=record.blocker_evidence_digest,
                disposition_authority_digest=record.disposition_authority_digest,
                gross=gross,
                employee_taxes=taxes,
                employee_deductions=deductions,
                net_pay=net,
                employer_contributions=employer,
                membership_digest=record.membership_digest,
            )
            if canonical_digest(member.canonical_content()) != record.membership_digest:
                raise PayrollConflictError("persisted Payroll membership was tampered")
            members.append(member)
        supersedes_identity = None
        if value.supersedes_run_id:
            supersedes_identity = await session.scalar(
                select(PayrollRunRecord.run_identity).where(
                    PayrollRunRecord.id == value.supersedes_run_id
                )
            )
        PayrollRunCandidate(
            company_id=value.company_id,
            pay_period_id=value.pay_period_id,
            schedule_definition_id=value.schedule_definition_id,
            schedule_version=value.schedule_version,
            assembly_version=value.assembly_version,
            population_identity=value.population_identity,
            population_digest=value.population_digest,
            currency=value.currency,
            members=tuple(members),
            aggregate_gross=value.aggregate_gross,
            aggregate_employee_taxes=value.aggregate_employee_taxes,
            aggregate_employee_deductions=value.aggregate_employee_deductions,
            aggregate_net_pay=value.aggregate_net_pay,
            aggregate_employer_contributions=value.aggregate_employer_contributions,
            run_identity=value.run_identity,
            run_digest=value.run_digest,
            assembled_at=value.assembled_at,
            supersedes_run_identity=supersedes_identity,
        ).verify()

    @staticmethod
    async def _locked_run(session: AsyncSession, context: AuthorizationContext, run_id: UUID) -> PayrollRunRecord:
        value = await session.scalar(select(PayrollRunRecord).where(PayrollRunRecord.company_id == context.company.id, PayrollRunRecord.id == run_id).with_for_update())
        if value is None:
            raise PayrollConflictError("Payroll run was not found")
        return value

    @staticmethod
    def _require(context: AuthorizationContext, permission: str) -> None:
        if not context.has_permission(permission):
            raise PayrollAuthorizationError("Payroll run permission denied")

    def _stage(self, session: AsyncSession, context: AuthorizationContext, value: PayrollRunRecord, event_type: EventType, action: str) -> None:
        details: dict[str, object] = {"run_identity": value.run_identity, "run_digest": value.run_digest, "pay_period_id": str(value.pay_period_id), "lifecycle": value.lifecycle}
        BusinessEventService.stage(session, BusinessEventCreate(event_type=event_type, entity_type="payroll_run", entity_id=value.id, company_id=value.company_id, user_id=context.user.id, payload=details))
        self._audit.stage(session, AuditEntry(action=action, resource_type="payroll_run", actor_user_id=context.user.id, company_id=value.company_id, resource_id=value.id, details=details))


payroll_run_service = PayrollRunService()
