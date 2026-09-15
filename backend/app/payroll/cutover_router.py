"""Protected Payroll cutover certification; contains no calculation or execution paths."""

from datetime import date, datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.payroll.contracts import canonical_digest
from app.payroll.models import (
    PayrollCutoverBridgeEmployeeFactRevision,
    PayrollCutoverBridgePeriodRecord,
    PayrollCutoverFactRevision,
    PayrollCutoverReviewRecord,
    PayrollPaymentDestinationVersion,
    PayrollProtectedInputEnvelope,
)
from app.payroll.permissions import PayrollPermission
from app.payroll.setup_router import _input_cipher
from app.platform.audit.service import AuditEntry, audit_service
from app.platform.employees.models import Employee
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.dependencies import require_permission

router = APIRouter(
    prefix="/api/v1/payroll/cutover-review", tags=["Payroll Cutover Review"]
)
Session = Annotated[AsyncSession, Depends(get_database_session)]
Read = Annotated[
    AuthorizationContext, Depends(require_permission(PayrollPermission.CUTOVER_READ))
]
Owner = Annotated[
    AuthorizationContext,
    Depends(require_permission(PayrollPermission.CUTOVER_OWNER_CERTIFY)),
]
Accountant = Annotated[
    AuthorizationContext,
    Depends(require_permission(PayrollPermission.CUTOVER_ACCOUNTANT_CERTIFY)),
]
Approver = Annotated[
    AuthorizationContext, Depends(require_permission(PayrollPermission.CUTOVER_APPROVE))
]

OWNER_FACTS = frozenset(
    {
        "employee_identity",
        "compensation_basis",
        "compensation_rate",
        "compensation_effective_date",
        "overtime_applicability",
        "w4_filing_status",
        "w4_step_2",
        "w4_step_3",
        "w4_step_4",
        "residence_jurisdiction",
        "work_jurisdiction",
        "deduction_applicability",
        "benefit_applicability",
        "final_quickbooks_period",
        "final_bridge_pay_date",
        "first_acp_period",
    }
)
ACCOUNTANT_FACTS = frozenset(
    {
        "gross_wages_ytd",
        "federal_taxable_wages_ytd",
        "federal_withholding_ytd",
        "social_security_wages_ytd",
        "social_security_employee_tax_ytd",
        "social_security_employer_tax_ytd",
        "medicare_wages_ytd",
        "medicare_employee_tax_ytd",
        "medicare_employer_tax_ytd",
        "state_local_ytd",
        "deduction_ytd",
        "benefit_ytd",
        "net_pay_ytd",
        "payroll_liabilities",
        "prior_period_coverage",
        "opening_ytd_boundary",
    }
)


def _stage_evidence(
    session: AsyncSession,
    context: AuthorizationContext,
    event_type: EventType,
    action: str,
    resource_type: str,
    resource_id: UUID,
    details: dict[str, object],
) -> None:
    BusinessEventService.stage(
        session,
        BusinessEventCreate(
            event_type=event_type,
            entity_type=resource_type,
            entity_id=resource_id,
            company_id=context.company.id,
            user_id=context.user.id,
            payload=details,
        ),
    )
    audit_service.stage(
        session,
        AuditEntry(
            action=action,
            resource_type=resource_type,
            actor_user_id=context.user.id,
            company_id=context.company.id,
            resource_id=resource_id,
            details=details,
        ),
    )


class ReviewCreate(BaseModel):
    proposed_legacy_period_end: date | None = None
    proposed_acp_period_start: date | None = None
    opening_ytd_effective_date: date | None = None


class FactWrite(BaseModel):
    review_id: UUID
    expected_review_version: int = Field(ge=1)
    employee_id: UUID | None = None
    fact_key: str = Field(min_length=1, max_length=120)
    candidate_reference: dict[str, object] = Field(default_factory=dict)
    candidate_classification: str = Field(min_length=1, max_length=64)
    action: Literal["confirm", "correct", "provide", "not_applicable"]
    certifier_role: Literal["owner", "accountant"]
    certified_value: object | None = None
    idempotency_key: str = Field(min_length=8, max_length=160)


class BridgePeriodWrite(BaseModel):
    review_id: UUID
    expected_review_version: int = Field(ge=1)
    period_start: date
    period_end: date
    pay_date: date
    source_type: Literal[
        "manual_paper_check", "legacy_provider", "other_certified_external"
    ]
    source_reference: str = Field(min_length=1, max_length=240)
    idempotency_key: str = Field(min_length=8, max_length=160)


class BridgeFactWrite(BaseModel):
    employee_id: UUID | None = None
    source_employee_reference: str | None = Field(default=None, max_length=240)
    fact_key: str = Field(min_length=1, max_length=120)
    certified_value: object
    certifier_role: Literal["owner", "accountant"]
    certify: bool = False
    idempotency_key: str = Field(min_length=8, max_length=160)


class BridgeCertification(BaseModel):
    certifier_role: Literal["owner", "accountant"]


async def _review(
    session: AsyncSession, company_id: UUID, review_id: UUID | None = None
) -> PayrollCutoverReviewRecord | None:
    query = select(PayrollCutoverReviewRecord).where(
        PayrollCutoverReviewRecord.company_id == company_id
    )
    if review_id is not None:
        query = query.where(PayrollCutoverReviewRecord.id == review_id)
    return await session.scalar(
        query.order_by(PayrollCutoverReviewRecord.version.desc())
    )


def _fact_projection(value: PayrollCutoverFactRevision) -> dict[str, object]:
    return {
        "id": str(value.id),
        "employee_id": str(value.employee_id) if value.employee_id else None,
        "fact_key": value.fact_key,
        "candidate_reference": value.candidate_reference,
        "candidate_classification": value.candidate_classification,
        "action": value.action,
        "certification_state": value.certification_state,
        "certifier_role": value.certifier_role,
        "certified_value": "••••" if value.protected_envelope_id else None,
        "certified_at": value.certified_at,
        "revision": value.revision,
        "evidence_digest": value.evidence_digest,
    }


@router.post("")
async def create_review(
    command: ReviewCreate, context: Owner, session: Session
) -> dict[str, object]:
    existing = await _review(session, context.company.id)
    if existing is not None:
        return {
            "id": str(existing.id),
            "version": existing.version,
            "lifecycle": existing.lifecycle,
        }
    value = PayrollCutoverReviewRecord(
        company_id=context.company.id,
        version=1,
        lifecycle="draft",
        proposed_legacy_period_end=command.proposed_legacy_period_end,
        proposed_acp_period_start=command.proposed_acp_period_start,
        opening_ytd_effective_date=command.opening_ytd_effective_date,
        created_by_user_id=context.user.id,
    )
    session.add(value)
    await session.flush()
    _stage_evidence(
        session,
        context,
        EventType.PAYROLL_CUTOVER_REVIEW_CREATED,
        "payroll.cutover_review.created",
        "payroll_cutover_review",
        value.id,
        {"version": value.version},
    )
    await session.commit()
    return {"id": str(value.id), "version": value.version, "lifecycle": value.lifecycle}


@router.get("")
async def get_review(context: Read, session: Session) -> dict[str, object]:
    review = await _review(session, context.company.id)
    employees = tuple(
        (
            await session.scalars(
                select(Employee)
                .where(Employee.company_id == context.company.id)
                .order_by(Employee.display_name)
            )
        ).all()
    )
    if review is None:
        return {
            "review": None,
            "employees": [
                {
                    "id": str(e.id),
                    "display_name": e.display_name,
                    "status": e.status,
                    "payroll_classification": "REVIEW_REQUIRED",
                }
                for e in employees
            ],
            "facts": [],
            "bridge_periods": [],
        }
    facts = tuple(
        (
            await session.scalars(
                select(PayrollCutoverFactRevision)
                .where(
                    PayrollCutoverFactRevision.company_id == context.company.id,
                    PayrollCutoverFactRevision.review_id == review.id,
                    PayrollCutoverFactRevision.certification_state != "superseded",
                )
                .order_by(PayrollCutoverFactRevision.fact_key)
            )
        ).all()
    )
    periods = tuple(
        (
            await session.scalars(
                select(PayrollCutoverBridgePeriodRecord)
                .where(
                    PayrollCutoverBridgePeriodRecord.company_id == context.company.id,
                    PayrollCutoverBridgePeriodRecord.review_id == review.id,
                )
                .order_by(PayrollCutoverBridgePeriodRecord.period_start)
            )
        ).all()
    )
    return {
        "review": {
            "id": str(review.id),
            "version": review.version,
            "lifecycle": review.lifecycle,
            "proposed_legacy_period_end": review.proposed_legacy_period_end,
            "proposed_acp_period_start": review.proposed_acp_period_start,
            "opening_ytd_effective_date": review.opening_ytd_effective_date,
        },
        "employees": [
            {
                "id": str(e.id),
                "display_name": e.display_name,
                "status": e.status,
                "payroll_classification": "REVIEW_REQUIRED",
            }
            for e in employees
        ],
        "facts": [_fact_projection(f) for f in facts],
        "bridge_periods": [
            {
                "id": str(p.id),
                "period_start": p.period_start,
                "period_end": p.period_end,
                "pay_date": p.pay_date,
                "source_type": p.source_type,
                "certification_state": p.certification_state,
                "source_reference": p.source_reference,
                "coverage_complete": p.coverage_complete,
            }
            for p in periods
        ],
    }


@router.get("/employees/{employee_id}")
async def employee_review(
    employee_id: UUID, context: Read, session: Session
) -> dict[str, object]:
    employee = await session.scalar(
        select(Employee).where(
            Employee.company_id == context.company.id, Employee.id == employee_id
        )
    )
    if employee is None:
        raise HTTPException(404, "Payroll cutover Employee was not found.")
    facts = tuple(
        (
            await session.scalars(
                select(PayrollCutoverFactRevision)
                .where(
                    PayrollCutoverFactRevision.company_id == context.company.id,
                    PayrollCutoverFactRevision.employee_id == employee_id,
                    PayrollCutoverFactRevision.certification_state != "superseded",
                )
                .order_by(PayrollCutoverFactRevision.fact_key)
            )
        ).all()
    )
    return {
        "employee": {
            "id": str(employee.id),
            "display_name": employee.display_name,
            "status": employee.status,
        },
        "facts": [_fact_projection(f) for f in facts],
    }


async def _write_fact(
    command: FactWrite,
    context: AuthorizationContext,
    session: AsyncSession,
    *,
    certified: bool,
) -> dict[str, object]:
    review = await _review(session, context.company.id, command.review_id)
    if review is None:
        raise HTTPException(404, "Payroll cutover review was not found.")
    existing = await session.scalar(
        select(PayrollCutoverFactRevision).where(
            PayrollCutoverFactRevision.company_id == context.company.id,
            PayrollCutoverFactRevision.actor_user_id == context.user.id,
            PayrollCutoverFactRevision.idempotency_key == command.idempotency_key,
        )
    )
    if existing:
        return _fact_projection(existing)
    if review.version != command.expected_review_version:
        raise HTTPException(
            409, "Payroll cutover review changed; refresh before saving."
        )
    allowed_candidate_keys = {
        "source",
        "source_id",
        "as_of",
        "evidence_digest",
        "classification",
    }
    if set(command.candidate_reference) - allowed_candidate_keys:
        raise HTTPException(
            422, "Candidate references may contain source metadata only."
        )
    if (
        command.employee_id
        and await session.scalar(
            select(Employee.id).where(
                Employee.company_id == context.company.id,
                Employee.id == command.employee_id,
            )
        )
        is None
    ):
        raise HTTPException(404, "Payroll cutover Employee was not found.")
    required = "accountant" if command.fact_key in ACCOUNTANT_FACTS else "owner"
    if certified and command.certifier_role != required:
        raise HTTPException(
            403,
            f"{required.title()} certification authority is required for this fact.",
        )
    previous = await session.scalar(
        select(PayrollCutoverFactRevision)
        .where(
            PayrollCutoverFactRevision.company_id == context.company.id,
            PayrollCutoverFactRevision.review_id == review.id,
            PayrollCutoverFactRevision.employee_id == command.employee_id,
            PayrollCutoverFactRevision.fact_key == command.fact_key,
            PayrollCutoverFactRevision.certification_state != "superseded",
        )
        .order_by(PayrollCutoverFactRevision.revision.desc())
        .with_for_update()
    )
    envelope_id = None
    protected_digest = None
    if command.action != "not_applicable":
        if command.certified_value is None:
            raise HTTPException(
                422, "A value is required; blank is never converted to zero."
            )
        cipher = _input_cipher()
        if cipher is None:
            raise HTTPException(
                503, "Protected Payroll input configuration is unavailable."
            )
        key_id, nonce, ciphertext, protected_digest = cipher.encrypt(
            company_id=context.company.id, payload={"value": command.certified_value}
        )
        envelope = PayrollProtectedInputEnvelope(
            company_id=context.company.id,
            key_id=key_id,
            nonce=nonce,
            ciphertext=ciphertext,
            content_digest=protected_digest,
            created_by_user_id=context.user.id,
        )
        session.add(envelope)
        await session.flush()
        envelope_id = envelope.id
    revision = 1 if previous is None else previous.revision + 1
    content = {
        "company_id": str(context.company.id),
        "review_id": str(review.id),
        "employee_id": str(command.employee_id) if command.employee_id else None,
        "fact_key": command.fact_key,
        "candidate_reference": command.candidate_reference,
        "candidate_classification": command.candidate_classification,
        "action": command.action,
        "state": "certified" if certified else "draft",
        "role": command.certifier_role,
        "revision": revision,
        "protected_digest": protected_digest,
    }
    value = PayrollCutoverFactRevision(
        company_id=context.company.id,
        review_id=review.id,
        employee_id=command.employee_id,
        fact_key=command.fact_key,
        candidate_reference=command.candidate_reference,
        candidate_classification=command.candidate_classification,
        protected_envelope_id=envelope_id,
        action=command.action,
        certification_state="certified" if certified else "draft",
        certifier_role=command.certifier_role,
        actor_user_id=context.user.id,
        certified_at=datetime.now(timezone.utc) if certified else None,
        revision=revision,
        supersedes_revision_id=previous.id if previous else None,
        idempotency_key=command.idempotency_key,
        evidence_digest=canonical_digest(content),
    )
    if previous:
        previous.certification_state = "superseded"
    session.add(value)
    review.lifecycle = "certification_in_progress"
    review.version += 1
    review.updated_at = datetime.now(timezone.utc)
    await session.flush()
    _stage_evidence(
        session,
        context,
        EventType.PAYROLL_CUTOVER_FACT_REVISED,
        "payroll.cutover_fact.certified"
        if certified
        else "payroll.cutover_fact.drafted",
        "payroll_cutover_fact",
        value.id,
        {
            "fact_key": command.fact_key,
            "employee_id": str(command.employee_id) if command.employee_id else None,
            "revision": revision,
            "certifier_role": command.certifier_role,
            "protected_value_present": envelope_id is not None,
        },
    )
    await session.commit()
    return _fact_projection(value)


@router.post("/facts")
async def save_fact(
    command: FactWrite, context: Owner, session: Session
) -> dict[str, object]:
    return await _write_fact(command, context, session, certified=False)


@router.post("/certifications")
async def certify_fact(
    command: FactWrite, context: Read, session: Session
) -> dict[str, object]:
    permission = (
        PayrollPermission.CUTOVER_ACCOUNTANT_CERTIFY
        if command.certifier_role == "accountant"
        else PayrollPermission.CUTOVER_OWNER_CERTIFY
    )
    if not context.has_permission(permission):
        raise HTTPException(403, "Required cutover certification authority is missing.")
    return await _write_fact(command, context, session, certified=True)


@router.post("/bridge-periods")
async def create_bridge_period(
    command: BridgePeriodWrite, context: Owner, session: Session
) -> dict[str, object]:
    if (
        command.period_end < command.period_start
        or command.pay_date < command.period_end
    ):
        raise HTTPException(422, "Bridge Payroll dates are invalid.")
    review = await _review(session, context.company.id, command.review_id)
    if review is None:
        raise HTTPException(404, "Payroll cutover review was not found.")
    existing = await session.scalar(
        select(PayrollCutoverBridgePeriodRecord).where(
            PayrollCutoverBridgePeriodRecord.company_id == context.company.id,
            PayrollCutoverBridgePeriodRecord.actor_user_id == context.user.id,
            PayrollCutoverBridgePeriodRecord.idempotency_key == command.idempotency_key,
        )
    )
    if existing is not None:
        return {
            "id": str(existing.id),
            "certification_state": existing.certification_state,
            "externally_calculated": True,
        }
    if review.version != command.expected_review_version:
        raise HTTPException(
            409, "Payroll cutover review changed; refresh before saving."
        )
    overlap = await session.scalar(
        select(PayrollCutoverBridgePeriodRecord.id).where(
            PayrollCutoverBridgePeriodRecord.company_id == context.company.id,
            PayrollCutoverBridgePeriodRecord.review_id == review.id,
            PayrollCutoverBridgePeriodRecord.certification_state != "superseded",
            and_(
                PayrollCutoverBridgePeriodRecord.period_start <= command.period_end,
                PayrollCutoverBridgePeriodRecord.period_end >= command.period_start,
            ),
        )
    )
    if overlap is not None:
        raise HTTPException(
            409, "Bridge Payroll period overlaps existing certified history."
        )
    if existing is None:
        existing = PayrollCutoverBridgePeriodRecord(
            company_id=context.company.id,
            review_id=review.id,
            period_start=command.period_start,
            period_end=command.period_end,
            pay_date=command.pay_date,
            source_type=command.source_type,
            certification_state="draft",
            source_reference=command.source_reference,
            coverage_complete=False,
            version=1,
            actor_user_id=context.user.id,
            idempotency_key=command.idempotency_key,
            evidence_digest=canonical_digest(command.model_dump(mode="json")),
        )
        session.add(existing)
        review.version += 1
        review.updated_at = datetime.now(timezone.utc)
        await session.flush()
        _stage_evidence(
            session,
            context,
            EventType.PAYROLL_CUTOVER_BRIDGE_REVISED,
            "payroll.cutover_bridge_period.drafted",
            "payroll_cutover_bridge_period",
            existing.id,
            {
                "period_start": command.period_start.isoformat(),
                "period_end": command.period_end.isoformat(),
                "pay_date": command.pay_date.isoformat(),
                "source_type": command.source_type,
            },
        )
        await session.commit()
    return {
        "id": str(existing.id),
        "certification_state": existing.certification_state,
        "externally_calculated": True,
    }


@router.post("/bridge-periods/{bridge_period_id}/facts")
async def write_bridge_fact(
    bridge_period_id: UUID, command: BridgeFactWrite, context: Read, session: Session
) -> dict[str, object]:
    permission = (
        PayrollPermission.CUTOVER_ACCOUNTANT_CERTIFY
        if command.certifier_role == "accountant"
        else PayrollPermission.CUTOVER_OWNER_CERTIFY
    )
    if not context.has_permission(permission):
        raise HTTPException(403, "Required bridge certification authority is missing.")
    if (command.employee_id is None) == (command.source_employee_reference is None):
        raise HTTPException(
            422,
            "Select exactly one ACP Employee or unresolved source Employee reference.",
        )
    period = await session.scalar(
        select(PayrollCutoverBridgePeriodRecord).where(
            PayrollCutoverBridgePeriodRecord.company_id == context.company.id,
            PayrollCutoverBridgePeriodRecord.id == bridge_period_id,
        )
    )
    if period is None:
        raise HTTPException(404, "Bridge Payroll period was not found.")
    if (
        command.employee_id
        and await session.scalar(
            select(Employee.id).where(
                Employee.company_id == context.company.id,
                Employee.id == command.employee_id,
            )
        )
        is None
    ):
        raise HTTPException(404, "Bridge Payroll Employee was not found.")
    existing = await session.scalar(
        select(PayrollCutoverBridgeEmployeeFactRevision).where(
            PayrollCutoverBridgeEmployeeFactRevision.company_id == context.company.id,
            PayrollCutoverBridgeEmployeeFactRevision.actor_user_id == context.user.id,
            PayrollCutoverBridgeEmployeeFactRevision.idempotency_key
            == command.idempotency_key,
        )
    )
    if existing:
        return {
            "id": str(existing.id),
            "certification_state": existing.certification_state,
            "certified_value": "••••",
        }
    previous = await session.scalar(
        select(PayrollCutoverBridgeEmployeeFactRevision)
        .where(
            PayrollCutoverBridgeEmployeeFactRevision.company_id == context.company.id,
            PayrollCutoverBridgeEmployeeFactRevision.bridge_period_id
            == bridge_period_id,
            PayrollCutoverBridgeEmployeeFactRevision.employee_id == command.employee_id,
            PayrollCutoverBridgeEmployeeFactRevision.source_employee_reference
            == command.source_employee_reference,
            PayrollCutoverBridgeEmployeeFactRevision.fact_key == command.fact_key,
        )
        .order_by(PayrollCutoverBridgeEmployeeFactRevision.revision.desc())
        .with_for_update()
    )
    cipher = _input_cipher()
    if cipher is None:
        raise HTTPException(
            503, "Protected Payroll input configuration is unavailable."
        )
    key_id, nonce, ciphertext, protected_digest = cipher.encrypt(
        company_id=context.company.id, payload={"value": command.certified_value}
    )
    envelope = PayrollProtectedInputEnvelope(
        company_id=context.company.id,
        key_id=key_id,
        nonce=nonce,
        ciphertext=ciphertext,
        content_digest=protected_digest,
        created_by_user_id=context.user.id,
    )
    session.add(envelope)
    await session.flush()
    value = PayrollCutoverBridgeEmployeeFactRevision(
        company_id=context.company.id,
        bridge_period_id=bridge_period_id,
        employee_id=command.employee_id,
        source_employee_reference=command.source_employee_reference,
        fact_key=command.fact_key,
        protected_envelope_id=envelope.id,
        certification_state="certified" if command.certify else "draft",
        certifier_role=command.certifier_role,
        actor_user_id=context.user.id,
        revision=1 if previous is None else previous.revision + 1,
        idempotency_key=command.idempotency_key,
        evidence_digest=canonical_digest(
            {
                "period": str(bridge_period_id),
                "employee": str(command.employee_id) if command.employee_id else None,
                "source_employee_reference": command.source_employee_reference,
                "fact_key": command.fact_key,
                "protected_digest": protected_digest,
            }
        ),
    )
    if previous:
        previous.certification_state = "superseded"
    session.add(value)
    await session.flush()
    _stage_evidence(
        session,
        context,
        EventType.PAYROLL_CUTOVER_BRIDGE_REVISED,
        "payroll.cutover_bridge_fact.certified"
        if command.certify
        else "payroll.cutover_bridge_fact.drafted",
        "payroll_cutover_bridge_fact",
        value.id,
        {
            "bridge_period_id": str(bridge_period_id),
            "employee_id": str(command.employee_id) if command.employee_id else None,
            "fact_key": command.fact_key,
            "revision": value.revision,
            "protected_value_present": True,
        },
    )
    await session.commit()
    return {
        "id": str(value.id),
        "certification_state": value.certification_state,
        "certified_value": "••••",
    }


@router.post("/bridge-periods/{bridge_period_id}/certify")
async def certify_bridge_period(
    bridge_period_id: UUID,
    command: BridgeCertification,
    context: Read,
    session: Session,
) -> dict[str, object]:
    permission = (
        PayrollPermission.CUTOVER_ACCOUNTANT_CERTIFY
        if command.certifier_role == "accountant"
        else PayrollPermission.CUTOVER_OWNER_CERTIFY
    )
    if not context.has_permission(permission):
        raise HTTPException(
            403, "Required bridge-period certification authority is missing."
        )
    period = await session.scalar(
        select(PayrollCutoverBridgePeriodRecord)
        .where(
            PayrollCutoverBridgePeriodRecord.company_id == context.company.id,
            PayrollCutoverBridgePeriodRecord.id == bridge_period_id,
        )
        .with_for_update()
    )
    if period is None:
        raise HTTPException(404, "Bridge Payroll period was not found.")
    facts = int(
        await session.scalar(
            select(func.count())
            .select_from(PayrollCutoverBridgeEmployeeFactRevision)
            .where(
                PayrollCutoverBridgeEmployeeFactRevision.company_id
                == context.company.id,
                PayrollCutoverBridgeEmployeeFactRevision.bridge_period_id
                == bridge_period_id,
                PayrollCutoverBridgeEmployeeFactRevision.certification_state
                == "certified",
            )
        )
        or 0
    )
    if facts == 0:
        raise HTTPException(
            409, "Bridge Employee facts must be certified before period coverage."
        )
    now = datetime.now(timezone.utc)
    if command.certifier_role == "owner":
        period.owner_certified_by_user_id = context.user.id
        period.owner_certified_at = now
    else:
        period.accountant_certified_by_user_id = context.user.id
        period.accountant_certified_at = now
    period.coverage_complete = (
        period.owner_certified_at is not None
        and period.accountant_certified_at is not None
    )
    period.certification_state = (
        "certified"
        if period.coverage_complete
        else f"{command.certifier_role}_certified"
    )
    period.version += 1
    _stage_evidence(
        session,
        context,
        EventType.PAYROLL_CUTOVER_BRIDGE_REVISED,
        "payroll.cutover_bridge_period.certified",
        "payroll_cutover_bridge_period",
        period.id,
        {
            "version": period.version,
            "certified_fact_count": facts,
            "externally_calculated": True,
        },
    )
    await session.commit()
    return {
        "id": str(period.id),
        "certification_state": period.certification_state,
        "coverage_complete": period.coverage_complete,
        "externally_calculated": True,
    }


async def _gates(
    context: AuthorizationContext, session: AsyncSession
) -> dict[str, object]:
    review = await _review(session, context.company.id)
    if review is None:
        return {"status": "BLOCKED", "blockers": ["CUTOVER_REVIEW_MISSING"]}
    facts = tuple(
        (
            await session.scalars(
                select(PayrollCutoverFactRevision).where(
                    PayrollCutoverFactRevision.company_id == context.company.id,
                    PayrollCutoverFactRevision.review_id == review.id,
                    PayrollCutoverFactRevision.certification_state == "certified",
                )
            )
        ).all()
    )
    present = {f.fact_key for f in facts}
    periods = tuple(
        (
            await session.scalars(
                select(PayrollCutoverBridgePeriodRecord).where(
                    PayrollCutoverBridgePeriodRecord.company_id == context.company.id,
                    PayrollCutoverBridgePeriodRecord.review_id == review.id,
                )
            )
        ).all()
    )
    blockers = [
        f"FACT_MISSING:{key}"
        for key in sorted((OWNER_FACTS | ACCOUNTANT_FACTS) - present)
    ]
    if not periods:
        blockers.append("MANUAL_BRIDGE_HISTORY_NOT_REVIEWED")
    if any(
        not p.coverage_complete or p.certification_state != "certified" for p in periods
    ):
        blockers.append("MANUAL_BRIDGE_PERIOD_UNCERTIFIED")
    return {
        "status": "BLOCKED" if blockers else "READY_FOR_CUTOVER_APPROVAL",
        "blockers": blockers,
        "review_id": str(review.id),
        "payroll_execution_enabled": False,
    }


@router.get("/gates")
async def gates(context: Read, session: Session) -> dict[str, object]:
    return await _gates(context, session)


@router.post("/approve")
async def approve(context: Approver, session: Session) -> dict[str, object]:
    result = await _gates(context, session)
    if result["status"] != "READY_FOR_CUTOVER_APPROVAL":
        raise HTTPException(409, "Payroll cutover gates remain incomplete.")
    review = await _review(session, context.company.id)
    assert review is not None
    review.lifecycle = "approved"
    review.approved_by_user_id = context.user.id
    review.approved_at = datetime.now(timezone.utc)
    review.version += 1
    _stage_evidence(
        session,
        context,
        EventType.PAYROLL_CUTOVER_REVIEW_APPROVED,
        "payroll.cutover_review.approved",
        "payroll_cutover_review",
        review.id,
        {"version": review.version, "payroll_execution_enabled": False},
    )
    await session.commit()
    return {"status": "APPROVED", "payroll_execution_enabled": False}


@router.get("/direct-deposit-readiness")
async def direct_deposit_readiness(
    context: Read, session: Session
) -> dict[str, object]:
    destination_count = int(
        await session.scalar(
            select(func.count())
            .select_from(PayrollPaymentDestinationVersion)
            .where(PayrollPaymentDestinationVersion.company_id == context.company.id)
        )
        or 0
    )
    blockers = [
        "DIRECT_DEPOSIT_PROVIDER_NOT_CONFIGURED",
        "EMPLOYER_FUNDING_ACCOUNT_NOT_CONFIGURED",
        "KYC_UNDERWRITING_NOT_COMPLETE",
        "ACH_ORIGINATION_NOT_AUTHORIZED",
        "FUNDING_CUTOFF_RULES_NOT_CONFIGURED",
        "RETURN_NOC_PROCESS_NOT_CONFIGURED",
        "SETTLEMENT_RECONCILIATION_NOT_CONFIGURED",
    ]
    if destination_count == 0:
        blockers += [
            "EMPLOYEE_PAYMENT_DESTINATIONS_NOT_ENROLLED",
            "EMPLOYEE_PAYMENT_AUTHORIZATION_NOT_CAPTURED",
        ]
    return {
        "status": "BLOCKED",
        "blockers": blockers,
        "employee_destination_count": destination_count,
        "can_initiate_ach": False,
    }
