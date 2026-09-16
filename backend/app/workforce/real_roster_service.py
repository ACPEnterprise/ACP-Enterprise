from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.operational_migration.models import HcpEmployeeSourceCrosswalk
from app.platform.audit.service import AuditEntry, audit_service
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership, MembershipBranchAccess
from app.platform.employees.models import Employee
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.models import MembershipRole, Role
from app.platform.users.models import User, UserCredential
from app.workforce.models import (
    Capability,
    RealWorkforceRosterBinding,
    WorkforceCapability,
    WorkforceCapabilityProfile,
    WorkforceWorkingAvailability,
)
from app.workforce.real_roster import (
    REAL_ALL_COUNTY_ROSTER,
    REAL_ALL_COUNTY_ROSTER_BY_KEY,
)
from app.workforce.schemas import (
    RealRosterReadiness,
    RealRosterReadinessItem,
    RealRosterSourceEvidence,
)


class RealRosterConflict(ValueError):
    pass


class RealRosterService:
    async def bind(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        roster_key: str,
        employee_id: UUID,
    ) -> RealRosterReadiness:
        if roster_key not in REAL_ALL_COUNTY_ROSTER_BY_KEY:
            raise RealRosterConflict("Roster identity is not owner-confirmed.")
        async with session.begin():
            employee = await session.scalar(
                select(Employee).where(
                    Employee.company_id == context.company.id,
                    Employee.id == employee_id,
                )
            )
            if employee is None:
                raise RealRosterConflict("Employee is not in the authorized Company.")
            existing = await session.scalar(
                select(RealWorkforceRosterBinding).where(
                    RealWorkforceRosterBinding.company_id == context.company.id,
                    RealWorkforceRosterBinding.roster_key == roster_key,
                )
            )
            competing = await session.scalar(
                select(RealWorkforceRosterBinding).where(
                    RealWorkforceRosterBinding.company_id == context.company.id,
                    RealWorkforceRosterBinding.employee_id == employee_id,
                    RealWorkforceRosterBinding.roster_key != roster_key,
                )
            )
            if competing is not None:
                raise RealRosterConflict("Employee is already bound to another roster identity.")
            if existing is None:
                binding = RealWorkforceRosterBinding(
                    company_id=context.company.id,
                    roster_key=roster_key,
                    employee_id=employee_id,
                    confirmed_by_user_id=context.user.id,
                )
                session.add(binding)
                await session.flush()
                active_branch = getattr(context, "active_branch", None)
                audit_service.stage(
                    session,
                    AuditEntry(
                        action="workforce.real_roster_identity_bound",
                        resource_type="real_workforce_roster_binding",
                        resource_id=binding.id,
                        actor_user_id=context.user.id,
                        company_id=context.company.id,
                        branch_id=(
                            active_branch.id
                            if active_branch is not None
                            else employee.home_branch_id
                        ),
                        details={
                            "roster_key": roster_key,
                            "employee_id": str(employee_id),
                            "authority": "explicit_owner_selection",
                        },
                    ),
                )
            elif existing.employee_id != employee_id:
                raise RealRosterConflict(
                    "Roster identity is already bound; owner review is required."
                )
        return await self.readiness(session, context=context)

    async def readiness(
        self, session: AsyncSession, *, context: AuthorizationContext
    ) -> RealRosterReadiness:
        bindings = {
            item.roster_key: item
            for item in (
                await session.scalars(
                    select(RealWorkforceRosterBinding).where(
                        RealWorkforceRosterBinding.company_id == context.company.id
                    )
                )
            ).all()
        }
        main_branch = await session.scalar(
            select(Branch).where(
                Branch.company_id == context.company.id,
                Branch.code == "MAIN",
                Branch.status == "active",
            )
        )
        items: list[RealRosterReadinessItem] = []
        for person in REAL_ALL_COUNTY_ROSTER:
            binding = bindings.get(person.key)
            if binding is None:
                items.append(self._unbound(person))
                continue
            employee = await session.scalar(
                select(Employee).where(
                    Employee.company_id == context.company.id,
                    Employee.id == binding.employee_id,
                )
            )
            if employee is None:
                items.append(self._unbound(person, blocker="BOUND_EMPLOYEE_MISSING"))
                continue
            membership = None
            user = None
            credential = None
            if employee.membership_id is not None:
                membership = await session.scalar(
                    select(Membership).where(
                        Membership.company_id == context.company.id,
                        Membership.id == employee.membership_id,
                    )
                )
            if membership is not None:
                user = await session.get(User, membership.user_id)
                if user is not None:
                    credential = await session.scalar(
                        select(UserCredential).where(UserCredential.user_id == user.id)
                    )
            role_codes: frozenset[str] = frozenset()
            if membership is not None:
                role_codes = frozenset(
                    await session.scalars(
                        select(Role.code)
                        .join(MembershipRole, MembershipRole.role_id == Role.id)
                        .where(
                            MembershipRole.company_id == context.company.id,
                            MembershipRole.membership_id == membership.id,
                            MembershipRole.revoked_at.is_(None),
                            Role.status == "active",
                            Role.archived_at.is_(None),
                        )
                    )
                )
            profile = await session.scalar(
                select(WorkforceCapabilityProfile).where(
                    WorkforceCapabilityProfile.company_id == context.company.id,
                    WorkforceCapabilityProfile.employee_id == employee.id,
                )
            )
            capability_codes: frozenset[str] = frozenset()
            if profile is not None:
                capability_codes = frozenset(
                    await session.scalars(
                        select(Capability.code)
                        .join(
                            WorkforceCapability,
                            WorkforceCapability.capability_id == Capability.id,
                        )
                        .where(
                            WorkforceCapability.company_id == context.company.id,
                            WorkforceCapability.profile_id == profile.id,
                            WorkforceCapability.status == "active",
                            Capability.status == "active",
                        )
                    )
                )
            now = datetime.now(timezone.utc)
            availability = None
            if profile is not None and main_branch is not None:
                availability = await session.scalar(
                    select(WorkforceWorkingAvailability)
                    .where(
                        WorkforceWorkingAvailability.company_id == context.company.id,
                        WorkforceWorkingAvailability.profile_id == profile.id,
                        WorkforceWorkingAvailability.branch_id == main_branch.id,
                        WorkforceWorkingAvailability.status == "available",
                        WorkforceWorkingAvailability.end_at > now,
                    )
                    .limit(1)
                )
            explicit_branch = False
            if membership is not None and main_branch is not None:
                explicit_branch = bool(
                    await session.scalar(
                        select(MembershipBranchAccess.id).where(
                            MembershipBranchAccess.membership_id == membership.id,
                            MembershipBranchAccess.branch_id == main_branch.id,
                        )
                    )
                )
            branch_ready = bool(
                main_branch
                and membership
                and (
                    membership.has_all_branch_access
                    or membership.default_branch_id == main_branch.id
                    or explicit_branch
                )
                and employee.home_branch_id == main_branch.id
            )
            user_ready = bool(user and user.status == "active" and user.archived_at is None)
            membership_ready = bool(membership and membership.status == "active")
            employee_ready = employee.status == "active" and employee.archived_at is None
            roles_ready = person.required_role_codes.issubset(role_codes)
            profile_ready = bool(profile and profile.status == "active")
            technician_ready = not person.field_tech or "technician" in capability_codes
            mobile_ready = not person.field_tech or "ACP_EMPLOYEE_MOBILE" in role_codes
            blockers = []
            for ready, code in (
                (user_ready, "USER_NOT_READY"),
                (employee_ready, "EMPLOYEE_NOT_READY"),
                (membership_ready, "MEMBERSHIP_NOT_READY"),
                (branch_ready, "MAIN_BRANCH_NOT_READY"),
                (roles_ready, "OPERATING_ROLE_NOT_READY"),
                (profile_ready, "WORKFORCE_PROFILE_NOT_READY"),
                (technician_ready, "TECHNICIAN_CAPABILITY_NOT_READY"),
                (mobile_ready, "MOBILE_ROLE_NOT_READY"),
            ):
                if not ready:
                    blockers.append(code)
            if credential is None:
                blockers.append("PASSWORD_NOT_ESTABLISHED")
            dispatch_ready = all(
                (employee_ready, branch_ready, profile_ready, technician_ready)
            ) if person.field_tech else False
            items.append(
                RealRosterReadinessItem(
                    roster_key=person.key,
                    display_name=person.display_name,
                    operating_role=person.role.value,
                    field_tech=person.field_tech,
                    employee_id=employee.id,
                    employee_display_name=employee.display_name,
                    user_state="USER_READY" if user_ready else "USER_MISSING_OR_INACTIVE",
                    employee_state="EMPLOYEE_READY" if employee_ready else "EMPLOYEE_MISSING_OR_INACTIVE",
                    membership_state="MEMBERSHIP_READY" if membership_ready else "MEMBERSHIP_MISSING_OR_INACTIVE",
                    branch_state="MAIN_BRANCH_READY" if branch_ready else "BRANCH_MISSING",
                    role_state="ROLE_READY" if roles_ready else "ROLE_MISSING",
                    workforce_profile_state="WORKFORCE_PROFILE_READY" if profile_ready else "WORKFORCE_PROFILE_MISSING",
                    technician_capability_state=("TECHNICIAN_CAPABILITY_READY" if technician_ready else "TECHNICIAN_CAPABILITY_MISSING"),
                    mobile_state="MOBILE_READY" if mobile_ready else "MOBILE_MISSING",
                    credential_state="ACP_LOGIN_READY" if credential else "BLOCKED_ACCOUNT_ACTIVATION",
                    availability_state="BOUNDED_EVIDENCE_PRESENT" if availability else "EXPLICIT_WINDOW_REQUIRED",
                    dispatch_state="READY_FOR_WINDOW_EVALUATION" if dispatch_ready else "NOT_DISPATCHABLE",
                    timekeeping_state="LINKED" if employee_ready and user_ready and membership_ready else "IDENTITY_LINKAGE_REQUIRED",
                    payroll_linkage_state="LINKED_INPUTS_NOT_EVALUATED" if employee_ready else "EMPLOYEE_BINDING_REQUIRED",
                    identity_confirmed_at=binding.created_at,
                    readiness_window_start_at=availability.start_at if availability else None,
                    readiness_window_end_at=availability.end_at if availability else None,
                    readiness_source=availability.source if availability else None,
                    blockers=tuple(blockers),
                )
            )
        source_evidence = await self._source_evidence(session, context, bindings)
        source_only_total = sum(
            item.certification_state == "SOURCE_ONLY" for item in source_evidence
        )
        certification_required_total = sum(
            item.certification_state == "OWNER_CERTIFICATION_REQUIRED"
            for item in source_evidence
        ) + sum(item.employee_id is None for item in items)
        return RealRosterReadiness(
            items=tuple(items),
            source_evidence=source_evidence,
            total=len(items),
            bound=sum(item.employee_id is not None for item in items),
            field_tech_total=sum(item.field_tech for item in items),
            field_tech_capability_ready=sum(
                item.field_tech
                and item.technician_capability_state == "TECHNICIAN_CAPABILITY_READY"
                for item in items
            ),
            source_evidence_total=len(source_evidence),
            source_only_total=source_only_total,
            certification_required_total=certification_required_total,
            login_ready_total=sum(
                item.credential_state == "ACP_LOGIN_READY" for item in items
            ),
            membership_ready_total=sum(
                item.membership_state == "MEMBERSHIP_READY" for item in items
            ),
            branch_ready_total=sum(
                item.branch_state == "MAIN_BRANCH_READY" for item in items
            ),
            mobile_ready_total=sum(
                item.mobile_state == "MOBILE_READY" for item in items
            ),
            dispatch_ready_total=sum(
                item.dispatch_state == "READY_FOR_WINDOW_EVALUATION" for item in items
            ),
            timekeeping_ready_total=sum(
                item.timekeeping_state == "LINKED" for item in items
            ),
            payroll_identity_ready_total=sum(
                item.payroll_linkage_state == "LINKED_INPUTS_NOT_EVALUATED"
                for item in items
            ),
        )

    @staticmethod
    async def _source_evidence(
        session: AsyncSession,
        context: AuthorizationContext,
        bindings: dict[str, RealWorkforceRosterBinding],
    ) -> tuple[RealRosterSourceEvidence, ...]:
        records = tuple(
            (
                await session.scalars(
                    select(HcpEmployeeSourceCrosswalk)
                    .where(HcpEmployeeSourceCrosswalk.company_id == context.company.id)
                    .order_by(
                        HcpEmployeeSourceCrosswalk.native_employee_id,
                        HcpEmployeeSourceCrosswalk.evidence_version.desc(),
                    )
                )
            ).all()
        )
        latest: dict[str, HcpEmployeeSourceCrosswalk] = {}
        for record in records:
            latest.setdefault(record.native_employee_id, record)
        roster_by_employee = {
            binding.employee_id: roster_key for roster_key, binding in bindings.items()
        }
        return tuple(
            RealRosterSourceEvidence(
                source_system="HCP",
                source_employee_id=record.native_employee_id,
                source_disposition=record.disposition,
                source_branch_id=record.branch_id,
                acp_employee_id=record.employee_id,
                roster_key=(
                    roster_by_employee.get(record.employee_id)
                    if record.employee_id is not None
                    else None
                ),
                certification_state=RealRosterService._source_certification_state(
                    disposition=record.disposition,
                    employee_id=record.employee_id,
                    roster_by_employee=roster_by_employee,
                ),
                evidence_version=record.evidence_version,
                recorded_at=record.recorded_at,
            )
            for record in latest.values()
        )

    @staticmethod
    def _source_certification_state(
        *,
        disposition: str,
        employee_id: UUID | None,
        roster_by_employee: dict[UUID, str],
    ) -> Literal[
        "ACP_EMPLOYEE_BOUND",
        "SOURCE_ONLY",
        "OWNER_CERTIFICATION_REQUIRED",
        "NOT_EMPLOYEE",
    ]:
        if disposition == "EXCLUDE_EMPLOYEE_HOLD_ASSIGNMENTS":
            return "NOT_EMPLOYEE"
        if employee_id is None:
            return "SOURCE_ONLY"
        if employee_id in roster_by_employee:
            return "ACP_EMPLOYEE_BOUND"
        return "OWNER_CERTIFICATION_REQUIRED"

    @staticmethod
    def _unbound(person, blocker: str = "OWNER_EMPLOYEE_BINDING_REQUIRED") -> RealRosterReadinessItem:
        return RealRosterReadinessItem(
            roster_key=person.key,
            display_name=person.display_name,
            operating_role=person.role.value,
            field_tech=person.field_tech,
            employee_id=None,
            employee_display_name=None,
            user_state="AUTHENTICATED_VERIFICATION_REQUIRED",
            employee_state="AUTHENTICATED_VERIFICATION_REQUIRED",
            membership_state="AUTHENTICATED_VERIFICATION_REQUIRED",
            branch_state="AUTHENTICATED_VERIFICATION_REQUIRED",
            role_state="AUTHENTICATED_VERIFICATION_REQUIRED",
            workforce_profile_state="AUTHENTICATED_VERIFICATION_REQUIRED",
            technician_capability_state="AUTHENTICATED_VERIFICATION_REQUIRED",
            mobile_state="AUTHENTICATED_VERIFICATION_REQUIRED",
            credential_state="AUTHENTICATED_VERIFICATION_REQUIRED",
            availability_state="AUTHENTICATED_VERIFICATION_REQUIRED",
            dispatch_state="AUTHENTICATED_VERIFICATION_REQUIRED",
            timekeeping_state="AUTHENTICATED_VERIFICATION_REQUIRED",
            payroll_linkage_state="AUTHENTICATED_VERIFICATION_REQUIRED",
            identity_confirmed_at=None,
            readiness_window_start_at=None,
            readiness_window_end_at=None,
            readiness_source=None,
            blockers=(blocker,),
        )


real_roster_service = RealRosterService()
