"""Durable gross-pay result and review authority.

Approval here accepts a gross-pay calculation result only. It does not finalize a
Payroll run, calculate tax/net pay, authorize payment, or post Accounting.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Select, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, AuditService, audit_service
from app.platform.permissions.authorization import AuthorizationContext
from app.timekeeping.models import PayrollTimeInputRecord

from .calculation import GrossPayCalculationResult
from .contracts import (
    PayrollAuthorizationError,
    PayrollConflictError,
    canonical_digest,
)
from .models import (
    CompanyPayrollPolicyVersion,
    EmployeeCompensationAuthorityVersion,
    PayrollGrossCalculationResultRecord,
    PayrollGrossCalculationReviewRecord,
)
from .permissions import PayrollPermission


class GrossResultLifecycle(StrEnum):
    CALCULATED = "calculated"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    SUPERSEDED = "superseded"
    VOIDED = "voided"


class GrossResultReviewState(StrEnum):
    NOT_STARTED = "not_started"
    UNDER_REVIEW = "under_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class GrossReviewDecision(StrEnum):
    INITIATED = "initiated"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class PayPeriodCalculationStatus:
    employee_id: UUID
    result_id: UUID | None
    result_identity: str | None
    status: str
    calculation_digest: str | None


class PayrollGrossResultService:
    def __init__(self, *, audit: AuditService = audit_service) -> None:
        self._audit = audit

    async def persist_candidate(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        candidate: GrossPayCalculationResult,
    ) -> PayrollGrossCalculationResultRecord:
        self._require(context, PayrollPermission.CALCULATION_EXECUTE)
        candidate.verify()
        if candidate.company_id != context.company.id:
            raise PayrollConflictError("gross-pay result Company scope mismatch")
        policy = await session.scalar(
            select(CompanyPayrollPolicyVersion).where(
                CompanyPayrollPolicyVersion.company_id == context.company.id,
                CompanyPayrollPolicyVersion.id == candidate.policy_id,
                CompanyPayrollPolicyVersion.authority_digest == candidate.policy_digest,
                CompanyPayrollPolicyVersion.lifecycle.in_(("approved", "superseded")),
            )
        )
        compensation = await session.scalar(
            select(EmployeeCompensationAuthorityVersion).where(
                EmployeeCompensationAuthorityVersion.company_id == context.company.id,
                EmployeeCompensationAuthorityVersion.id
                == candidate.compensation_authority_id,
                EmployeeCompensationAuthorityVersion.employee_id
                == candidate.employee_id,
                EmployeeCompensationAuthorityVersion.authority_digest
                == candidate.compensation_digest,
                EmployeeCompensationAuthorityVersion.lifecycle.in_(
                    ("approved", "superseded")
                ),
            )
        )
        if policy is None or compensation is None:
            raise PayrollConflictError("gross-pay authority evidence is unavailable")
        if candidate.time_snapshot_id is not None:
            time_input = await session.scalar(
                select(PayrollTimeInputRecord).where(
                    PayrollTimeInputRecord.company_id == context.company.id,
                    PayrollTimeInputRecord.employee_id == candidate.employee_id,
                    PayrollTimeInputRecord.pay_period_id
                    == candidate.pay_period.pay_period_id,
                    PayrollTimeInputRecord.snapshot_identity
                    == candidate.time_snapshot_id,
                    PayrollTimeInputRecord.snapshot_digest
                    == candidate.time_snapshot_digest,
                )
            )
            if time_input is None:
                raise PayrollConflictError("gross-pay time evidence is unavailable")
        await self._subject_lock(
            session,
            company_id=context.company.id,
            employee_id=candidate.employee_id,
            pay_period_id=candidate.pay_period.pay_period_id,
        )
        existing = await session.scalar(
            select(PayrollGrossCalculationResultRecord).where(
                PayrollGrossCalculationResultRecord.company_id == context.company.id,
                PayrollGrossCalculationResultRecord.calculation_digest
                == candidate.calculation_digest,
            )
        )
        if existing is not None:
            if existing.result_identity != candidate.result_id:
                raise PayrollConflictError("gross-pay persistence identity conflict")
            return existing
        active = await session.scalar(
            self._active_query(
                context.company.id,
                candidate.employee_id,
                candidate.pay_period.pay_period_id,
            ).with_for_update()
        )
        prior = None
        if candidate.supersedes_result_id is not None:
            prior = await session.scalar(
                select(PayrollGrossCalculationResultRecord)
                .where(
                    PayrollGrossCalculationResultRecord.company_id
                    == context.company.id,
                    PayrollGrossCalculationResultRecord.result_identity
                    == candidate.supersedes_result_id,
                )
                .with_for_update()
            )
            if (
                prior is None
                or prior.id != (active.id if active else None)
                or prior.employee_id != candidate.employee_id
                or prior.pay_period_id != candidate.pay_period.pay_period_id
                or prior.lifecycle
                not in {
                    GrossResultLifecycle.CALCULATED.value,
                    GrossResultLifecycle.UNDER_REVIEW.value,
                    GrossResultLifecycle.APPROVED.value,
                }
            ):
                raise PayrollConflictError("gross-pay supersession lineage conflict")
            prior.lifecycle = GrossResultLifecycle.SUPERSEDED.value
            await session.flush()
        elif active is not None:
            raise PayrollConflictError("active gross-pay result already exists")
        value = PayrollGrossCalculationResultRecord(
            id=uuid4(),
            company_id=candidate.company_id,
            employee_id=candidate.employee_id,
            pay_period_id=candidate.pay_period.pay_period_id,
            period_start=candidate.pay_period.period_start,
            period_end=candidate.pay_period.period_end,
            result_identity=candidate.result_id,
            calculation_version=candidate.definition_version,
            currency=candidate.currency,
            policy_id=candidate.policy_id,
            policy_digest=candidate.policy_digest,
            compensation_authority_id=candidate.compensation_authority_id,
            compensation_digest=candidate.compensation_digest,
            time_snapshot_id=candidate.time_snapshot_id,
            time_snapshot_digest=candidate.time_snapshot_digest,
            admission_id=candidate.admission_id,
            admission_digest=candidate.admission_digest,
            earning_components=[item.canonical_content() for item in candidate.components],
            gross_pay_total=candidate.gross_pay_total,
            calculation_digest=candidate.calculation_digest,
            calculated_at=candidate.calculated_at,
            created_by_user_id=context.user.id,
            lifecycle=GrossResultLifecycle.CALCULATED.value,
            review_state=GrossResultReviewState.NOT_STARTED.value,
            supersedes_result_id=prior.id if prior else None,
        )
        session.add(value)
        await session.flush()
        if prior is not None:
            self._stage(
                session,
                context=context,
                value=prior,
                event_type=EventType.PAYROLL_GROSS_CALCULATION_SUPERSEDED,
                action="payroll.gross_calculation.superseded",
                details={
                    "calculation_digest": prior.calculation_digest,
                    "successor_digest": candidate.calculation_digest,
                },
            )
        self._stage(
            session,
            context=context,
            value=value,
            event_type=EventType.PAYROLL_GROSS_CALCULATION_PERSISTED,
            action="payroll.gross_calculation.persisted",
            details={
                "calculation_digest": value.calculation_digest,
                "lifecycle": value.lifecycle,
            },
        )
        await session.commit()
        return value

    async def initiate_review(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        result_id: UUID,
        reason_code: str,
        safe_note: str | None = None,
        reviewed_at: datetime | None = None,
    ) -> PayrollGrossCalculationReviewRecord:
        self._require(context, PayrollPermission.CALCULATION_REVIEW)
        value = await self._locked_result(session, context, result_id)
        if value.lifecycle not in {
            GrossResultLifecycle.CALCULATED.value,
            GrossResultLifecycle.APPROVED.value,
        }:
            raise PayrollConflictError("gross-pay result cannot enter review")
        value.lifecycle = GrossResultLifecycle.UNDER_REVIEW.value
        value.review_state = GrossResultReviewState.UNDER_REVIEW.value
        record = await self._review_record(
            session,
            context=context,
            value=value,
            decision=GrossReviewDecision.INITIATED,
            reason_code=reason_code,
            safe_note=safe_note,
            reviewed_at=reviewed_at,
        )
        self._stage(
            session,
            context=context,
            value=value,
            event_type=EventType.PAYROLL_GROSS_REVIEW_INITIATED,
            action="payroll.gross_review.initiated",
            details={"calculation_digest": value.calculation_digest},
        )
        await session.commit()
        return record

    async def decide_review(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        result_id: UUID,
        decision: GrossReviewDecision,
        reason_code: str,
        safe_note: str | None = None,
        reviewed_at: datetime | None = None,
    ) -> PayrollGrossCalculationReviewRecord:
        self._require(context, PayrollPermission.CALCULATION_REVIEW)
        if decision not in {GrossReviewDecision.ACCEPTED, GrossReviewDecision.REJECTED}:
            raise PayrollConflictError("gross-pay review decision is invalid")
        value = await self._locked_result(session, context, result_id)
        if (
            value.lifecycle != GrossResultLifecycle.UNDER_REVIEW.value
            or value.review_state != GrossResultReviewState.UNDER_REVIEW.value
        ):
            raise PayrollConflictError("gross-pay result is not under review")
        if decision is GrossReviewDecision.ACCEPTED:
            value.lifecycle = GrossResultLifecycle.APPROVED.value
            value.review_state = GrossResultReviewState.ACCEPTED.value
            event_type = EventType.PAYROLL_GROSS_REVIEW_ACCEPTED
        else:
            value.lifecycle = GrossResultLifecycle.CALCULATED.value
            value.review_state = GrossResultReviewState.REJECTED.value
            event_type = EventType.PAYROLL_GROSS_REVIEW_REJECTED
        record = await self._review_record(
            session,
            context=context,
            value=value,
            decision=decision,
            reason_code=reason_code,
            safe_note=safe_note,
            reviewed_at=reviewed_at,
        )
        self._stage(
            session,
            context=context,
            value=value,
            event_type=event_type,
            action=f"payroll.gross_review.{decision.value}",
            details={
                "calculation_digest": value.calculation_digest,
                "decision": decision.value,
            },
        )
        await session.commit()
        return record

    async def result(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        result_id: UUID,
    ) -> PayrollGrossCalculationResultRecord:
        self._require(context, PayrollPermission.CALCULATION_READ)
        value = await session.scalar(
            select(PayrollGrossCalculationResultRecord).where(
                PayrollGrossCalculationResultRecord.company_id == context.company.id,
                PayrollGrossCalculationResultRecord.id == result_id,
            )
        )
        if value is None:
            raise PayrollConflictError("gross-pay result was not found")
        return value

    async def period_results(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        pay_period_id: UUID,
        blocked: tuple[PayPeriodCalculationStatus, ...] = (),
    ) -> tuple[PayPeriodCalculationStatus, ...]:
        self._require(context, PayrollPermission.CALCULATION_READ)
        values = await session.scalars(
            select(PayrollGrossCalculationResultRecord)
            .where(
                PayrollGrossCalculationResultRecord.company_id == context.company.id,
                PayrollGrossCalculationResultRecord.pay_period_id == pay_period_id,
            )
            .order_by(
                PayrollGrossCalculationResultRecord.employee_id,
                PayrollGrossCalculationResultRecord.created_at,
            )
        )
        persisted = tuple(
            PayPeriodCalculationStatus(
                item.employee_id,
                item.id,
                item.result_identity,
                item.lifecycle,
                item.calculation_digest,
            )
            for item in values.all()
        )
        return tuple(sorted((*persisted, *blocked), key=lambda item: str(item.employee_id)))

    async def history(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        employee_id: UUID,
        pay_period_id: UUID,
    ) -> tuple[PayrollGrossCalculationResultRecord, ...]:
        self._require(context, PayrollPermission.CALCULATION_READ)
        values = await session.scalars(
            select(PayrollGrossCalculationResultRecord)
            .where(
                PayrollGrossCalculationResultRecord.company_id == context.company.id,
                PayrollGrossCalculationResultRecord.employee_id == employee_id,
                PayrollGrossCalculationResultRecord.pay_period_id == pay_period_id,
            )
            .order_by(PayrollGrossCalculationResultRecord.created_at)
        )
        return tuple(values.all())

    async def _locked_result(
        self, session: AsyncSession, context: AuthorizationContext, result_id: UUID
    ) -> PayrollGrossCalculationResultRecord:
        value = await session.scalar(
            select(PayrollGrossCalculationResultRecord)
            .where(
                PayrollGrossCalculationResultRecord.company_id == context.company.id,
                PayrollGrossCalculationResultRecord.id == result_id,
            )
            .with_for_update()
        )
        if value is None:
            raise PayrollConflictError("gross-pay result was not found")
        return value

    async def _review_record(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        value: PayrollGrossCalculationResultRecord,
        decision: GrossReviewDecision,
        reason_code: str,
        safe_note: str | None,
        reviewed_at: datetime | None,
    ) -> PayrollGrossCalculationReviewRecord:
        reason = reason_code.strip()
        note = safe_note.strip() if safe_note else None
        if not reason or len(reason) > 80 or (note and (len(note) > 500 or "$" in note)):
            raise PayrollConflictError("gross-pay review evidence is unsafe")
        sequence = (
            await session.scalar(
                select(func.count(PayrollGrossCalculationReviewRecord.id)).where(
                    PayrollGrossCalculationReviewRecord.result_id == value.id
                )
            )
            or 0
        ) + 1
        occurred_at = reviewed_at or datetime.now(timezone.utc)
        digest = canonical_digest(
            {
                "result_id": str(value.id),
                "result_digest": value.calculation_digest,
                "review_sequence": sequence,
                "reviewer_user_id": str(context.user.id),
                "decision": decision.value,
                "reason_code": reason,
                "safe_note": note,
                "reviewed_at": occurred_at.isoformat(),
            }
        )
        record = PayrollGrossCalculationReviewRecord(
            id=uuid4(),
            company_id=context.company.id,
            result_id=value.id,
            review_sequence=sequence,
            reviewer_user_id=context.user.id,
            decision=decision.value,
            reason_code=reason,
            safe_note=note,
            result_digest=value.calculation_digest,
            review_digest=digest,
            reviewed_at=occurred_at,
        )
        session.add(record)
        await session.flush()
        return record

    @staticmethod
    async def _subject_lock(
        session: AsyncSession,
        *,
        company_id: UUID,
        employee_id: UUID,
        pay_period_id: UUID,
    ) -> None:
        key = f"payroll-gross:{company_id}:{employee_id}:{pay_period_id}"
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": key},
        )

    @staticmethod
    def _active_query(
        company_id: UUID, employee_id: UUID, pay_period_id: UUID
    ) -> Select[tuple[PayrollGrossCalculationResultRecord]]:
        return select(PayrollGrossCalculationResultRecord).where(
            PayrollGrossCalculationResultRecord.company_id == company_id,
            PayrollGrossCalculationResultRecord.employee_id == employee_id,
            PayrollGrossCalculationResultRecord.pay_period_id == pay_period_id,
            PayrollGrossCalculationResultRecord.lifecycle.in_(
                (
                    GrossResultLifecycle.CALCULATED.value,
                    GrossResultLifecycle.UNDER_REVIEW.value,
                    GrossResultLifecycle.APPROVED.value,
                )
            ),
        )

    @staticmethod
    def _require(context: AuthorizationContext, permission: str) -> None:
        if not context.has_permission(permission):
            raise PayrollAuthorizationError("Payroll calculation permission denied")

    def _stage(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        value: PayrollGrossCalculationResultRecord,
        event_type: EventType,
        action: str,
        details: dict[str, object],
    ) -> None:
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type="payroll_gross_calculation",
                entity_id=value.id,
                company_id=context.company.id,
                user_id=context.user.id,
                payload=details,
            ),
        )
        self._audit.stage(
            session,
            AuditEntry(
                action=action,
                resource_type="payroll_gross_calculation",
                actor_user_id=context.user.id,
                company_id=context.company.id,
                resource_id=value.id,
                details=details,
            ),
        )


payroll_gross_result_service = PayrollGrossResultService()
