from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.employees.models import Employee
from app.platform.permissions.authorization import AuthorizationContext
from app.workforce.models import WorkforceCapabilityProfile
from app.workforce.query import WorkforceEligibilityQuery
from app.workforce.query_service import workforce_eligibility_service
from app.workforce.records import WorkforceCapabilityProfileRecord
from app.workforce.repository import workforce_capability_repository
from app.workforce.schemas import (
    WorkforceBranchItem,
    WorkforceCapabilityItem,
    WorkforceCertificationItem,
    WorkforceDirectory,
    WorkforceEligibilityItem,
    WorkforceEligibilityRequest,
    WorkforceEligibilityResponse,
    WorkforceEmployeeDetail,
    WorkforceEmployeeSummary,
    WorkforceLanguageItem,
)


class WorkforceOperationsService:
    @staticmethod
    def _readiness(employee: Employee, profile: WorkforceCapabilityProfileRecord | None) -> tuple[Literal["READY", "BLOCKED", "INSUFFICIENT_EVIDENCE"], tuple[str, ...]]:
        blockers: list[str] = []
        if employee.status != "active" or employee.archived_at is not None:
            blockers.append("employee_inactive")
        if profile is None:
            blockers.append("capability_profile_missing")
            return "INSUFFICIENT_EVIDENCE", tuple(blockers)
        if profile.status != "active":
            blockers.append("profile_inactive")
        active_codes = {item.code for item in profile.capabilities if item.status == "active"}
        if "technician" not in active_codes:
            blockers.append("technician_capability_missing")
        today = datetime.now(timezone.utc).date()
        if any(item.status != "active" or (item.expires_on is not None and item.expires_on < today) for item in profile.certifications):
            blockers.append("credential_not_current")
        if not any(item.status == "active" for item in profile.branch_eligibilities) and employee.home_branch_id is None:
            blockers.append("branch_authority_missing")
        if blockers:
            return "BLOCKED", tuple(blockers)
        return "READY", ()

    @classmethod
    def _summary(cls, employee: Employee, profile: WorkforceCapabilityProfileRecord | None) -> WorkforceEmployeeSummary:
        readiness, blockers = cls._readiness(employee, profile)
        capabilities = tuple(item.code for item in profile.capabilities if item.status == "active") if profile else ()
        languages = tuple(item.code for item in profile.languages if item.status == "active") if profile else ()
        return WorkforceEmployeeSummary(
            employee_id=employee.id, employee_number=employee.employee_number,
            display_name=employee.display_name, job_title=employee.job_title,
            employee_type=employee.employee_type, employee_status=employee.status,
            home_branch_id=employee.home_branch_id, profile_id=profile.id if profile else None,
            profile_status=profile.status if profile else None, technician="technician" in capabilities,
            capability_codes=capabilities, language_codes=languages,
            readiness_state=readiness, readiness_blockers=blockers,
            updated_at=max(employee.updated_at, profile.updated_at) if profile else employee.updated_at,
        )

    async def directory(self, session: AsyncSession, *, context: AuthorizationContext) -> WorkforceDirectory:
        rows = (await session.execute(
            select(Employee, WorkforceCapabilityProfile)
            .outerjoin(WorkforceCapabilityProfile, and_(
                WorkforceCapabilityProfile.company_id == Employee.company_id,
                WorkforceCapabilityProfile.employee_id == Employee.id,
            ))
            .where(Employee.company_id == context.company.id)
            .order_by(Employee.display_name, Employee.id)
        )).all()
        items = []
        for employee, profile_model in rows:
            profile = None if profile_model is None else await workforce_capability_repository.get_complete_profile(
                session, company_id=context.company.id, profile_id=profile_model.id
            )
            if employee.home_branch_id is None or context.can_access_branch(employee.home_branch_id):
                items.append(self._summary(employee, profile))
        return WorkforceDirectory(items=tuple(items), total=len(items))

    async def detail(self, session: AsyncSession, *, context: AuthorizationContext, employee_id: UUID) -> WorkforceEmployeeDetail | None:
        employee = await session.scalar(select(Employee).where(Employee.company_id == context.company.id, Employee.id == employee_id))
        if employee is None or (employee.home_branch_id is not None and not context.can_access_branch(employee.home_branch_id)):
            return None
        profile_id = await session.scalar(select(WorkforceCapabilityProfile.id).where(WorkforceCapabilityProfile.company_id == context.company.id, WorkforceCapabilityProfile.employee_id == employee_id))
        if profile_id is None:
            summary = self._summary(employee, None)
            return WorkforceEmployeeDetail(**summary.model_dump(), capabilities=(), certifications=(), languages=(), branches=(), work_restrictions=(), equipment_capabilities=())
        complete = await workforce_capability_repository.get_complete_profile(session, company_id=context.company.id, profile_id=profile_id)
        if complete is None:
            return None
        summary = self._summary(employee, complete)
        return WorkforceEmployeeDetail(
            **summary.model_dump(),
            capabilities=tuple(WorkforceCapabilityItem(code=i.code, display_name=i.display_name, proficiency=i.proficiency, status=i.status) for i in complete.capabilities),
            certifications=tuple(WorkforceCertificationItem(code=i.code, display_name=i.display_name, credential_reference=i.credential_reference, status=i.status, issued_on=i.issued_on, expires_on=i.expires_on) for i in complete.certifications),
            languages=tuple(WorkforceLanguageItem(code=i.code, english_name=i.english_name, native_name=i.native_name, spoken_proficiency=i.spoken_proficiency, customer_facing_eligible=i.customer_facing_eligible, interpreter_verified=i.interpreter_verified, status=i.status) for i in complete.languages),
            branches=tuple(WorkforceBranchItem(branch_id=i.branch_id, status=i.status, starts_on=i.starts_on, ends_on=i.ends_on) for i in complete.branch_eligibilities if context.can_access_branch(i.branch_id)),
            work_restrictions=tuple(i.code for i in complete.work_restrictions if i.status == "active"),
            equipment_capabilities=tuple(WorkforceCapabilityItem(code=i.code, display_name=i.display_name, proficiency=i.proficiency, status=i.status) for i in complete.equipment_capabilities),
        )

    async def eligibility(self, session: AsyncSession, *, context: AuthorizationContext, request: WorkforceEligibilityRequest) -> WorkforceEligibilityResponse:
        rows = await workforce_eligibility_service.eligible_technicians(session, context=context, query=WorkforceEligibilityQuery(
            company_id=context.company.id, authorized_branch_ids=context.authorized_branch_ids,
            branch_id=request.branch_id, window_start_at=request.window_start_at,
            window_end_at=request.window_end_at, required_capability_codes=request.required_capability_codes,
            required_language_codes=request.required_language_codes,
        ))
        return WorkforceEligibilityResponse(items=tuple(WorkforceEligibilityItem(**item.__dict__) for item in rows))


workforce_operations_service = WorkforceOperationsService()
