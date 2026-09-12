"""Operator-facing Payroll setup over existing effective-dated authorities."""

import base64
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.session import get_database_session
from app.payroll.commands import DraftCompensationAuthority
from app.payroll.contracts import (
    CompensationType,
    PayrollAuthorityError,
    PayrollAuthorizationError,
    PayrollConflictError,
    canonical_digest,
)
from app.payroll.models import (
    EmployeeCompensationAuthorityVersion,
    PayrollInputAuthorityVersion,
    PayrollProtectedInputEnvelope,
    PayrollRunMemberRecord,
    PayrollRunRecord,
)
from app.payroll.operations import PayrollOperationsService
from app.payroll.permissions import PayrollPermission
from app.payroll.real_employee_readiness_wiring import (
    REFERENCE_VERSION,
    AssemblyEvidence,
    SetupValue,
    assemble_real_employee_readiness,
)
from app.payroll.service import payroll_authority_service
from app.payroll.tax_authority import (
    AuthorityApplicability,
    DraftPayrollInputAuthority,
    PayrollInputAuthorityService,
    PayrollInputDomain,
    ProtectedPayrollInputCipher,
)
from app.platform.employees.models import Employee
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.dependencies import (
    require_any_permission,
    require_permission,
)
from app.timekeeping.models import PayPeriod, PayrollTimeInputRecord

router = APIRouter(prefix="/api/v1/payroll/setup", tags=["Payroll Setup"])
Session = Annotated[AsyncSession, Depends(get_database_session)]
SetupRead = Annotated[
    AuthorizationContext,
    Depends(
        require_any_permission(
            PayrollPermission.COMPENSATION_READ,
            PayrollPermission.TAX_AUTHORITY_READ,
            PayrollPermission.DEDUCTION_AUTHORITY_READ,
        )
    ),
]
CompManage = Annotated[
    AuthorizationContext,
    Depends(require_permission(PayrollPermission.COMPENSATION_MANAGE)),
]
CompApprove = Annotated[
    AuthorizationContext,
    Depends(require_permission(PayrollPermission.COMPENSATION_APPROVE)),
]
InputManage = Annotated[
    AuthorizationContext,
    Depends(
        require_any_permission(
            PayrollPermission.TAX_AUTHORITY_MANAGE,
            PayrollPermission.DEDUCTION_AUTHORITY_MANAGE,
        )
    ),
]
InputApprove = Annotated[
    AuthorizationContext,
    Depends(
        require_any_permission(
            PayrollPermission.TAX_AUTHORITY_APPROVE,
            PayrollPermission.DEDUCTION_AUTHORITY_APPROVE,
        )
    ),
]


class CompensationDraft(BaseModel):
    effective_start: date
    effective_end: date | None = None
    compensation_type: Literal["hourly", "salaried"]
    hourly_rate: Decimal | None = Field(default=None, gt=0)
    salary_amount: Decimal | None = Field(default=None, gt=0)
    salary_frequency: str | None = None
    worker_class_reference: str | None = None
    supersedes_authority_id: UUID | None = None
    audit_reason: str = Field(min_length=3, max_length=500)


class InputDraft(BaseModel):
    domain: Literal["tax", "deduction", "employer_contribution"]
    authority_key: str = Field(min_length=1, max_length=120)
    applicability: Literal["required", "not_applicable"] = "required"
    effective_start: date
    effective_end: date | None = None
    jurisdiction_reference: str | None = Field(default=None, max_length=160)
    calculation_basis: str | None = Field(default=None, max_length=80)
    priority: int | None = Field(default=None, ge=0)
    public_parameters: dict[str, object] = Field(default_factory=dict)
    protected_values: dict[str, object] | None = None
    supersedes_authority_id: UUID | None = None
    audit_reason: str = Field(min_length=3, max_length=500)


class EmployeeReadinessProjection(BaseModel):
    contract_version: str
    readiness_contract_version: str
    employee_id: UUID
    pay_period_id: UUID
    status: str
    calculation_readiness: list[str]
    exact_blockers: list[str]
    provider_version: str | None
    reconciliation_version: str | None
    evidence_digest: str


_SUPPORTED_INPUT_KEYS = {
    "w4_filing_status",
    "w4_step_2",
    "w4_step_3",
    "w4_step_4a",
    "w4_step_4b",
    "w4_step_4c",
    "work_jurisdiction",
    "residence_jurisdiction",
    "state_local_withholding_configuration",
    "unemployment_workforce_jurisdiction",
    "deduction_configuration",
    "deduction_tax_treatment",
    "deduction_effective_date",
    "deduction_limits",
    "social_security_wages_ytd",
    "social_security_tax_ytd",
    "social_security_applicability",
    "medicare_wages_ytd",
    "medicare_tax_ytd",
    "medicare_applicability",
    "additional_medicare_prerequisites",
    "federal_withholding_ytd",
    "prior_payroll_coverage",
    "federal_tax_table",
    "state_local_tax_table",
    "tax_table_source_version",
    "tax_table_effective_date",
}
_SUPPORTED_PROTECTED_FIELDS = {"value"}
_DEDUCTION_INPUT_KEYS = {
    "deduction_configuration",
    "deduction_tax_treatment",
    "deduction_effective_date",
    "deduction_limits",
}


def _input_cipher() -> ProtectedPayrollInputCipher | None:
    if not settings.payroll_input_active_kid:
        return None
    try:
        configured_keys = settings.payroll_input_encryption_keys
        if settings.payroll_input_encryption_key_file:
            key_file = Path(settings.payroll_input_encryption_key_file)
            configured_keys = json.loads(key_file.read_text(encoding="utf-8"))
            if not isinstance(configured_keys, dict):
                raise ValueError("Payroll input keyring must be a JSON object.")
        keys = {
            key: base64.urlsafe_b64decode(value)
            for key, value in configured_keys.items()
        }
        return ProtectedPayrollInputCipher(
            active_key_id=settings.payroll_input_active_kid, keys=keys
        )
    except Exception as error:
        raise HTTPException(
            503, "Protected Payroll input configuration is unavailable."
        ) from error


def _input_service() -> PayrollInputAuthorityService:
    return PayrollInputAuthorityService(cipher=_input_cipher())


def _comp(value: EmployeeCompensationAuthorityVersion) -> dict[str, object]:
    return {
        "id": str(value.id),
        "version": value.authority_version,
        "lifecycle": value.lifecycle,
        "effective_start": value.effective_start,
        "effective_end": value.effective_end,
        "compensation_type": value.compensation_type,
        "hourly_rate": str(value.hourly_rate)
        if value.hourly_rate is not None
        else None,
        "salary_amount": str(value.salary_amount)
        if value.salary_amount is not None
        else None,
        "salary_frequency": value.salary_frequency,
        "worker_class_reference": value.worker_class_reference,
        "supersedes_authority_id": str(value.supersedes_authority_id)
        if value.supersedes_authority_id
        else None,
    }


def _input(value: PayrollInputAuthorityVersion) -> dict[str, object]:
    return {
        "id": str(value.id),
        "domain": value.authority_domain,
        "key": value.authority_key,
        "version": value.authority_version,
        "lifecycle": value.lifecycle,
        "applicability": value.applicability,
        "effective_start": value.effective_start,
        "effective_end": value.effective_end,
        "jurisdiction_reference": value.jurisdiction_reference,
        "calculation_basis": value.calculation_basis,
        "priority": value.priority,
        "public_parameters": value.public_parameters,
        "protected_values_present": value.protected_envelope_id is not None,
        "supersedes_authority_id": str(value.supersedes_authority_id)
        if value.supersedes_authority_id
        else None,
    }


@router.get("/employees/{employee_id}")
async def employee_setup(
    employee_id: UUID, context: SetupRead, session: Session
) -> dict[str, object]:
    employee = await session.scalar(
        select(Employee).where(
            Employee.company_id == context.company.id, Employee.id == employee_id
        )
    )
    if employee is None:
        raise HTTPException(404, "Employee Payroll setup was not found.")
    compensations = (
        tuple(
            (
                await session.scalars(
                    select(EmployeeCompensationAuthorityVersion)
                    .where(
                        EmployeeCompensationAuthorityVersion.company_id
                        == context.company.id,
                        EmployeeCompensationAuthorityVersion.employee_id == employee_id,
                    )
                    .order_by(
                        EmployeeCompensationAuthorityVersion.authority_version.desc()
                    )
                )
            ).all()
        )
        if context.has_permission(PayrollPermission.COMPENSATION_READ)
        else ()
    )
    readable_domains: list[str] = []
    if context.has_permission(PayrollPermission.TAX_AUTHORITY_READ):
        readable_domains.append(PayrollInputDomain.TAX.value)
    if context.has_permission(PayrollPermission.DEDUCTION_AUTHORITY_READ):
        readable_domains.extend(
            (
                PayrollInputDomain.DEDUCTION.value,
                PayrollInputDomain.EMPLOYER_CONTRIBUTION.value,
            )
        )
    inputs = (
        tuple(
            (
                await session.scalars(
                    select(PayrollInputAuthorityVersion)
                    .where(
                        PayrollInputAuthorityVersion.company_id == context.company.id,
                        PayrollInputAuthorityVersion.employee_id == employee_id,
                        PayrollInputAuthorityVersion.authority_domain.in_(
                            readable_domains
                        ),
                    )
                    .order_by(
                        PayrollInputAuthorityVersion.authority_domain,
                        PayrollInputAuthorityVersion.authority_key,
                        PayrollInputAuthorityVersion.authority_version.desc(),
                    )
                )
            ).all()
        )
        if readable_domains
        else ()
    )
    member = await session.scalar(
        select(PayrollRunMemberRecord)
        .join(PayrollRunRecord, PayrollRunRecord.id == PayrollRunMemberRecord.run_id)
        .where(
            PayrollRunMemberRecord.company_id == context.company.id,
            PayrollRunMemberRecord.employee_id == employee_id,
        )
        .order_by(PayrollRunRecord.assembled_at.desc(), PayrollRunRecord.id.desc())
    )
    blockers = (
        list(member.blocker_codes) if member and member.disposition == "blocked" else []
    )
    ready = bool(member and member.disposition == "ready")
    return {
        "employee_id": str(employee.id),
        "employee_name": employee.display_name,
        "employee_number": employee.employee_number,
        "readiness": "READY_FOR_PAYROLL" if ready else "BLOCKED_FOR_PAYROLL",
        "blockers": blockers or ([] if ready else ["PAYROLL_RUN_ADMISSION_REQUIRED"]),
        "compensations": [_comp(value) for value in compensations],
        "inputs": [_input(value) for value in inputs],
        "protected_input_configuration_ready": bool(
            settings.payroll_input_active_kid
            and (
                settings.payroll_input_encryption_keys
                or settings.payroll_input_encryption_key_file
            )
        ),
    }


@router.get(
    "/employees/{employee_id}/readiness",
    response_model=EmployeeReadinessProjection,
)
async def employee_readiness(
    employee_id: UUID,
    pay_period_id: UUID,
    context: SetupRead,
    session: Session,
) -> EmployeeReadinessProjection:
    """Project exact readiness blockers without returning protected input values."""
    employee = await session.scalar(
        select(Employee).where(
            Employee.company_id == context.company.id, Employee.id == employee_id
        )
    )
    period = await session.scalar(
        select(PayPeriod).where(
            PayPeriod.company_id == context.company.id, PayPeriod.id == pay_period_id
        )
    )
    if employee is None or period is None:
        raise HTTPException(404, "Employee Payroll readiness was not found.")
    try:
        operating = await PayrollOperationsService().period(
            session, context=context, pay_period_id=pay_period_id
        )
    except PayrollAuthorizationError as error:
        raise HTTPException(403, "Payroll readiness authority is required.") from error
    operating_employee = next(
        (value for value in operating.employees if value.employee_id == employee_id), None
    )
    compensation_rows = tuple(
        (
            await session.scalars(
                select(EmployeeCompensationAuthorityVersion).where(
                    EmployeeCompensationAuthorityVersion.company_id
                    == context.company.id,
                    EmployeeCompensationAuthorityVersion.employee_id == employee_id,
                    EmployeeCompensationAuthorityVersion.lifecycle.in_(
                        ("approved", "superseded")
                    ),
                    EmployeeCompensationAuthorityVersion.effective_start
                    <= period.period_end,
                    (
                        EmployeeCompensationAuthorityVersion.effective_end.is_(None)
                        | (
                            EmployeeCompensationAuthorityVersion.effective_end
                            >= period.period_start
                        )
                    ),
                )
            )
        ).all()
    )
    superseded_compensation_ids = {
        value.supersedes_authority_id
        for value in compensation_rows
        if value.supersedes_authority_id is not None
    }
    compensations = tuple(
        value
        for value in compensation_rows
        if value.id not in superseded_compensation_ids
        and value.lifecycle == "approved"
    )
    compensation = compensations[0] if len(compensations) == 1 else None
    try:
        setup_values = await _readiness_setup_values(
            session,
            company_id=context.company.id,
            employee_id=employee_id,
            period_start=period.period_start,
            period_end=period.period_end,
        )
    except (PayrollAuthorityError, PayrollConflictError) as error:
        raise HTTPException(409, "Payroll readiness evidence is unavailable.") from error
    time_snapshot = await session.scalar(
        select(PayrollTimeInputRecord)
        .where(
            PayrollTimeInputRecord.company_id == context.company.id,
            PayrollTimeInputRecord.employee_id == employee_id,
            PayrollTimeInputRecord.pay_period_id == pay_period_id,
        )
        .order_by(PayrollTimeInputRecord.created_at.desc())
    )
    time_ready = bool(
        operating_employee is not None
        and operating_employee.time_snapshot_state == "CURRENT"
        and time_snapshot is not None
    )
    try:
        assembly = assemble_real_employee_readiness(
            AssemblyEvidence(
                context.company.id,
                employee.home_branch_id,
                employee.id,
                employee.status == "active",
                period.period_start,
                period.period_end,
                compensation.salary_frequency if compensation is not None else None,
                compensation.compensation_type if compensation is not None else None,
                compensation.id if compensation is not None else None,
                compensation.effective_start if compensation is not None else None,
                compensation.effective_end if compensation is not None else None,
                employee.id if time_ready else None,
                time_snapshot.snapshot_digest if time_ready and time_snapshot else None,
                setup_values,
                REFERENCE_VERSION,
            )
        )
    except (PayrollAuthorityError, PayrollConflictError, ValueError) as error:
        raise HTTPException(409, "Payroll readiness evidence is unavailable.") from error
    readiness = assembly.readiness.employees[0]
    return EmployeeReadinessProjection(
        contract_version="payroll.real-employee-readiness-runtime.v1",
        readiness_contract_version=assembly.readiness.contract_version,
        employee_id=employee.id,
        pay_period_id=period.id,
        status=(
            "READY_FOR_PAYROLL"
            if readiness.status.value == "PAYROLL_READY"
            else readiness.status.value
        ),
        calculation_readiness=[value.value for value in readiness.calculation_readiness],
        exact_blockers=list(readiness.exact_blockers),
        provider_version=assembly.provider_version,
        reconciliation_version=REFERENCE_VERSION,
        evidence_digest=assembly.assembly_digest,
    )


async def _readiness_setup_values(
    session: AsyncSession,
    *,
    company_id: UUID,
    employee_id: UUID,
    period_start: date,
    period_end: date,
) -> tuple[SetupValue, ...]:
    rows = tuple(
        (
            await session.scalars(
                select(PayrollInputAuthorityVersion).where(
                    PayrollInputAuthorityVersion.company_id == company_id,
                    PayrollInputAuthorityVersion.employee_id == employee_id,
                    PayrollInputAuthorityVersion.lifecycle.in_(
                        ("approved", "superseded")
                    ),
                    PayrollInputAuthorityVersion.effective_start <= period_end,
                    (
                        PayrollInputAuthorityVersion.effective_end.is_(None)
                        | (PayrollInputAuthorityVersion.effective_end >= period_start)
                    ),
                )
            )
        ).all()
    )
    superseded_ids = {
        value.supersedes_authority_id
        for value in rows
        if value.supersedes_authority_id is not None
    }
    active = tuple(value for value in rows if value.id not in superseded_ids)
    envelope_ids = tuple(
        value.protected_envelope_id
        for value in active
        if value.protected_envelope_id is not None
    )
    envelopes = {
        value.id: value
        for value in (
            (
                await session.scalars(
                    select(PayrollProtectedInputEnvelope).where(
                        PayrollProtectedInputEnvelope.company_id == company_id,
                        PayrollProtectedInputEnvelope.id.in_(envelope_ids),
                    )
                )
            ).all()
            if envelope_ids
            else ()
        )
    }
    cipher = _input_cipher() if envelope_ids else None
    if envelope_ids and cipher is None:
        raise HTTPException(503, "Protected Payroll input configuration is unavailable.")
    result: list[SetupValue] = []
    for value in active:
        envelope = (
            envelopes.get(value.protected_envelope_id)
            if value.protected_envelope_id is not None
            else None
        )
        if envelope is not None and cipher is not None:
            payload = cipher.decrypt(
                company_id=company_id,
                key_id=envelope.key_id,
                nonce=envelope.nonce,
                ciphertext=envelope.ciphertext,
                expected_digest=envelope.content_digest,
            )
            resolved = payload.get("value")
        elif value.applicability == "not_applicable":
            resolved = "not_applicable"
        else:
            continue
        result.append(
            SetupValue(
                value.authority_key,
                employee_id,
                period_end.year,
                value.effective_start,
                value.effective_end,
                value.id,
                value.authority_version,
                value.authority_digest,
                envelope.content_digest
                if envelope is not None
                else value.evidence_digest,
                resolved,
            )
        )
    return tuple(result)


@router.post("/employees/{employee_id}/compensations", status_code=201)
async def draft_compensation(
    employee_id: UUID, body: CompensationDraft, context: CompManage, session: Session
) -> dict[str, object]:
    if (
        await session.scalar(
            select(Employee.id).where(
                Employee.company_id == context.company.id, Employee.id == employee_id
            )
        )
        is None
    ):
        raise HTTPException(404, "Employee Payroll setup was not found.")
    prior = await session.scalar(
        select(EmployeeCompensationAuthorityVersion)
        .where(
            EmployeeCompensationAuthorityVersion.company_id == context.company.id,
            EmployeeCompensationAuthorityVersion.employee_id == employee_id,
        )
        .order_by(EmployeeCompensationAuthorityVersion.authority_version.desc())
    )
    command = DraftCompensationAuthority(
        employee_id=employee_id,
        authority_version=(prior.authority_version + 1 if prior else 1),
        effective_start=body.effective_start,
        effective_end=body.effective_end,
        compensation_type=CompensationType(body.compensation_type),
        hourly_rate=body.hourly_rate,
        salary_amount=body.salary_amount,
        salary_frequency=body.salary_frequency,
        worker_class_reference=body.worker_class_reference,
        additional_earning_types=(),
        recurring_components=(),
        decision_evidence_digest=canonical_digest(body.model_dump(mode="json")),
        audit_reason=body.audit_reason,
        supersedes_authority_id=body.supersedes_authority_id,
    )
    try:
        return _comp(
            await payroll_authority_service.draft_compensation(
                session, context=context, command=command
            )
        )
    except (PayrollAuthorityError, PayrollConflictError) as error:
        raise HTTPException(409, str(error)) from error


@router.post("/compensations/{authority_id}/approve")
async def approve_compensation(
    authority_id: UUID, context: CompApprove, session: Session
) -> dict[str, object]:
    try:
        return _comp(
            await payroll_authority_service.approve_compensation(
                session, context=context, authority_id=authority_id
            )
        )
    except (PayrollAuthorityError, PayrollConflictError) as error:
        raise HTTPException(409, str(error)) from error


@router.post("/employees/{employee_id}/inputs", status_code=201)
async def draft_input(
    employee_id: UUID, body: InputDraft, context: InputManage, session: Session
) -> dict[str, object]:
    if (
        await session.scalar(
            select(Employee.id).where(
                Employee.company_id == context.company.id, Employee.id == employee_id
            )
        )
        is None
    ):
        raise HTTPException(404, "Employee Payroll setup was not found.")
    if body.authority_key not in _SUPPORTED_INPUT_KEYS:
        raise HTTPException(
            422, "Payroll input key is not supported by this operating contract."
        )
    expected_domain = (
        "deduction" if body.authority_key in _DEDUCTION_INPUT_KEYS else "tax"
    )
    if body.domain != expected_domain:
        raise HTTPException(
            422, "Payroll input key does not match its authoritative domain."
        )
    if body.protected_values and not set(body.protected_values).issubset(
        _SUPPORTED_PROTECTED_FIELDS
    ):
        raise HTTPException(422, "Protected Payroll input contains unsupported fields.")
    domain = PayrollInputDomain(body.domain)
    permission = (
        PayrollPermission.TAX_AUTHORITY_MANAGE
        if domain is PayrollInputDomain.TAX
        else PayrollPermission.DEDUCTION_AUTHORITY_MANAGE
    )
    if not context.has_permission(permission):
        raise HTTPException(403, "Permission denied.")
    prior = await session.scalar(
        select(PayrollInputAuthorityVersion)
        .where(
            PayrollInputAuthorityVersion.company_id == context.company.id,
            PayrollInputAuthorityVersion.employee_id == employee_id,
            PayrollInputAuthorityVersion.authority_domain == body.domain,
            PayrollInputAuthorityVersion.authority_key == body.authority_key,
        )
        .order_by(PayrollInputAuthorityVersion.authority_version.desc())
    )
    command = DraftPayrollInputAuthority(
        employee_id=employee_id,
        domain=domain,
        authority_key=body.authority_key,
        authority_version=(prior.authority_version + 1 if prior else 1),
        applicability=AuthorityApplicability(body.applicability),
        effective_start=body.effective_start,
        effective_end=body.effective_end,
        jurisdiction_reference=body.jurisdiction_reference,
        calculation_basis=body.calculation_basis,
        priority=body.priority,
        public_parameters=body.public_parameters,
        protected_payload=body.protected_values,
        evidence_digest=canonical_digest(body.model_dump(mode="json")),
        audit_reason=body.audit_reason,
        supersedes_authority_id=body.supersedes_authority_id,
    )
    try:
        return _input(
            await _input_service().draft(session, context=context, command=command)
        )
    except (PayrollAuthorityError, PayrollConflictError) as error:
        raise HTTPException(409, str(error)) from error


@router.post("/inputs/{authority_id}/approve")
async def approve_input(
    authority_id: UUID, context: InputApprove, session: Session
) -> dict[str, object]:
    try:
        return _input(
            await _input_service().approve(
                session, context=context, authority_id=authority_id
            )
        )
    except (PayrollAuthorityError, PayrollConflictError) as error:
        raise HTTPException(409, str(error)) from error
