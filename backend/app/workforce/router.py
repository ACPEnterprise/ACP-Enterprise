from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AdministrationPermission, WorkforcePermission
from app.platform.permissions.dependencies import require_permission
from app.platform.reliability.correlation import current_correlation_id
from app.platform.reliability.failures import ClientRecovery, FailureCode, SafeFailure
from app.workforce.administration_commands import (
    WorkforceAdministrationConflict,
    workforce_administration_service,
)
from app.workforce.employee_administration import employee_administration_service
from app.workforce.real_roster_service import RealRosterConflict, real_roster_service
from app.workforce.schemas import (
    AvailabilityEvidenceRequest,
    CapabilityEvidenceRequest,
    CertificationEvidenceRequest,
    EmployeeAdministrationDetail,
    FieldReadinessRequest,
    FieldReadinessResponse,
    LanguageEvidenceRequest,
    RealRosterBindingRequest,
    RealRosterReadiness,
    SourceCertificationDecisionRequest,
    SourceCertificationLedger,
    WorkforceDirectory,
    WorkforceEligibilityRequest,
    WorkforceEligibilityResponse,
    WorkforceEmployeeDetail,
    WorkforceEvidenceResponse,
    WorkforceProfileResponse,
)
from app.workforce.service import workforce_operations_service
from app.workforce.source_certification import (
    SourceCertificationConflict,
    source_certification_service,
)

router = APIRouter(prefix="/api/v1/workforce", tags=["Workforce"])
Session = Annotated[AsyncSession, Depends(get_database_session)]
ReadContext = Annotated[
    AuthorizationContext, Depends(require_permission(WorkforcePermission.READ))
]
ManageContext = Annotated[
    AuthorizationContext, Depends(require_permission(WorkforcePermission.MANAGE))
]
CapabilityManageContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(WorkforcePermission.CAPABILITY_MANAGE)),
]
CertificationManageContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(WorkforcePermission.CERTIFICATION_MANAGE)),
]
AvailabilityManageContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(WorkforcePermission.AVAILABILITY_MANAGE)),
]


def _require_employee_administration(context: AuthorizationContext) -> None:
    required = {
        AdministrationPermission.MEMBERSHIP_READ,
        AdministrationPermission.ROLE_READ,
    }
    if not required.issubset(context.permission_codes):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Employee administration authority is required."
        )


def _workforce_conflict(error: ValueError) -> HTTPException:
    failure = SafeFailure(
        FailureCode.RESOURCE_STATE_CONFLICT,
        "Workforce evidence conflicts with current authority.",
        ClientRecovery.RETRY_AFTER_REFRESH,
        current_correlation_id(),
    )
    return HTTPException(status.HTTP_409_CONFLICT, failure.detail())


@router.get("/employees", response_model=WorkforceDirectory)
async def directory(context: ReadContext, session: Session) -> WorkforceDirectory:
    return await workforce_operations_service.directory(session, context=context)


@router.get("/real-roster", response_model=RealRosterReadiness)
async def real_roster(context: ReadContext, session: Session) -> RealRosterReadiness:
    return await real_roster_service.readiness(session, context=context)


@router.put("/real-roster/{roster_key}/binding", response_model=RealRosterReadiness)
async def bind_real_roster_employee(
    roster_key: str,
    data: RealRosterBindingRequest,
    context: CapabilityManageContext,
    session: Session,
) -> RealRosterReadiness:
    try:
        return await real_roster_service.bind(
            session,
            context=context,
            roster_key=roster_key,
            employee_id=data.employee_id,
        )
    except RealRosterConflict as error:
        raise _workforce_conflict(error) from error


@router.get("/source-certifications", response_model=SourceCertificationLedger)
async def source_certifications(
    context: CertificationManageContext, session: Session
) -> SourceCertificationLedger:
    return await source_certification_service.ledger(session, context=context)


@router.put(
    "/source-certifications/HCP/{source_employee_id}",
    response_model=SourceCertificationLedger,
)
async def decide_source_certification(
    source_employee_id: str,
    data: SourceCertificationDecisionRequest,
    context: CertificationManageContext,
    session: Session,
) -> SourceCertificationLedger:
    try:
        return await source_certification_service.decide(
            session,
            context=context,
            source_employee_id=source_employee_id,
            command=data,
        )
    except SourceCertificationConflict as error:
        raise _workforce_conflict(error) from error


@router.get("/employees/{employee_id}", response_model=WorkforceEmployeeDetail)
async def detail(
    employee_id: UUID, context: ReadContext, session: Session
) -> WorkforceEmployeeDetail:
    result = await workforce_operations_service.detail(
        session, context=context, employee_id=employee_id
    )
    if result is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Workforce profile was not found."
        )
    return result


@router.get(
    "/administration/employees/{employee_id}",
    response_model=EmployeeAdministrationDetail,
)
async def administration_detail(
    employee_id: UUID,
    context: ManageContext,
    session: Session,
) -> EmployeeAdministrationDetail:
    _require_employee_administration(context)
    result = await employee_administration_service.detail(
        session, context=context, employee_id=employee_id
    )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee was not found.")
    return result


@router.put(
    "/administration/employees/{employee_id}/profile",
    response_model=WorkforceProfileResponse,
)
async def ensure_profile(
    employee_id: UUID, context: ManageContext, session: Session
) -> WorkforceProfileResponse:
    try:
        profile, _created = await workforce_administration_service.ensure_profile(
            session, context=context, employee_id=employee_id
        )
    except WorkforceAdministrationConflict as error:
        raise _workforce_conflict(error) from error
    return WorkforceProfileResponse(
        id=profile.id,
        employee_id=profile.employee_id,
        status=profile.status,
        concurrency_version=profile.concurrency_version,
    )


@router.put(
    "/administration/employees/{employee_id}/capabilities",
    response_model=WorkforceEvidenceResponse,
)
async def record_capability(
    employee_id: UUID,
    data: CapabilityEvidenceRequest,
    context: CapabilityManageContext,
    session: Session,
) -> WorkforceEvidenceResponse:
    try:
        evidence_id, created = await workforce_administration_service.add_capability(
            session,
            context=context,
            employee_id=employee_id,
            capability_id=data.capability_id,
            proficiency=data.proficiency,
        )
    except WorkforceAdministrationConflict as error:
        raise _workforce_conflict(error) from error
    return WorkforceEvidenceResponse(id=evidence_id, created=created)


@router.put(
    "/administration/employees/{employee_id}/certifications",
    response_model=WorkforceEvidenceResponse,
)
async def record_certification(
    employee_id: UUID,
    data: CertificationEvidenceRequest,
    context: CertificationManageContext,
    session: Session,
) -> WorkforceEvidenceResponse:
    try:
        evidence_id, created = await workforce_administration_service.add_certification(
            session,
            context=context,
            employee_id=employee_id,
            certification_id=data.certification_id,
            credential_reference=data.credential_reference,
            status=data.status,
            issued_on=data.issued_on,
            expires_on=data.expires_on,
        )
    except WorkforceAdministrationConflict as error:
        raise _workforce_conflict(error) from error
    return WorkforceEvidenceResponse(id=evidence_id, created=created)


@router.put(
    "/administration/employees/{employee_id}/languages",
    response_model=WorkforceEvidenceResponse,
)
async def record_language(
    employee_id: UUID,
    data: LanguageEvidenceRequest,
    context: CapabilityManageContext,
    session: Session,
) -> WorkforceEvidenceResponse:
    try:
        evidence_id, created = await workforce_administration_service.add_language(
            session,
            context=context,
            employee_id=employee_id,
            language_id=data.language_id,
            spoken_proficiency=data.spoken_proficiency,
            customer_facing_eligible=data.customer_facing_eligible,
        )
    except WorkforceAdministrationConflict as error:
        raise _workforce_conflict(error) from error
    return WorkforceEvidenceResponse(id=evidence_id, created=created)


@router.put(
    "/administration/employees/{employee_id}/availability",
    response_model=WorkforceEvidenceResponse,
)
async def record_availability(
    employee_id: UUID,
    data: AvailabilityEvidenceRequest,
    context: AvailabilityManageContext,
    session: Session,
) -> WorkforceEvidenceResponse:
    try:
        evidence_id, created = await workforce_administration_service.add_availability(
            session,
            context=context,
            employee_id=employee_id,
            branch_id=data.branch_id,
            start_at=data.start_at,
            end_at=data.end_at,
            status=data.status,
            source=data.source,
        )
    except WorkforceAdministrationConflict as error:
        raise _workforce_conflict(error) from error
    return WorkforceEvidenceResponse(id=evidence_id, created=created)


@router.put(
    "/administration/employees/{employee_id}/field-readiness",
    response_model=FieldReadinessResponse,
)
async def prepare_field_readiness(
    employee_id: UUID,
    data: FieldReadinessRequest,
    context: CapabilityManageContext,
    session: Session,
) -> FieldReadinessResponse:
    if not context.has_permission(WorkforcePermission.AVAILABILITY_MANAGE):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Availability management authority is required."
        )
    try:
        profile_id, capability_id, availability_id = (
            await workforce_administration_service.prepare_field_readiness(
                session, context=context, employee_id=employee_id,
                branch_id=data.branch_id, start_at=data.window_start_at,
                end_at=data.window_end_at, reason=data.reason,
            )
        )
    except WorkforceAdministrationConflict as error:
        raise _workforce_conflict(error) from error
    return FieldReadinessResponse(
        profile_id=profile_id,
        capability_evidence_id=capability_id,
        availability_evidence_id=availability_id,
    )


@router.post("/eligibility", response_model=WorkforceEligibilityResponse)
async def eligibility(
    payload: WorkforceEligibilityRequest, context: ReadContext, session: Session
) -> WorkforceEligibilityResponse:
    return await workforce_operations_service.eligibility(
        session, context=context, request=payload
    )
