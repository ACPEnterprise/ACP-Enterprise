from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.operational_migration.models import HcpEmployeeSourceCrosswalk
from app.platform.auth.services import normalize_email
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership
from app.platform.employees.models import Employee
from app.platform.onboarding.models import IdentityOnboardingRequest
from app.platform.onboarding.service import (
    OnboardingCommand,
    identity_onboarding_service,
)
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AdministrationPermission
from app.platform.permissions.models import Role
from app.platform.users.models import User
from app.workforce.employee_identity_classification import employee_is_synthetic
from app.workforce.real_roster import REAL_ALL_COUNTY_ROSTER, RealRosterAdmission


class SimpleOnboardingConflict(ValueError):
    pass


class MatchOutcome(StrEnum):
    NONE = "NONE"
    SINGLE = "SINGLE"
    AMBIGUOUS = "AMBIGUOUS"


class AccessProfile(StrEnum):
    ADMINISTRATOR = "ADMINISTRATOR"
    OFFICE_MANAGER = "OFFICE_MANAGER"
    OFFICE_STAFF = "OFFICE_STAFF"
    FIELD_TECHNICIAN = "FIELD_TECHNICIAN"
    FIELD_MANAGER = "FIELD_MANAGER"


ROLE_CODES = {
    AccessProfile.ADMINISTRATOR: frozenset({"COMPANY_ADMINISTRATOR"}),
    AccessProfile.OFFICE_MANAGER: frozenset({"OFFICE_MANAGER"}),
    AccessProfile.OFFICE_STAFF: frozenset({"SERVICE_CSR"}),
    AccessProfile.FIELD_TECHNICIAN: frozenset({"TECHNICIAN", "ACP_EMPLOYEE_MOBILE"}),
    # Field Manager is a reusable composite profile: assigned field execution
    # plus the existing dispatcher supervision authority. It deliberately
    # excludes administration, Payroll, accounting, and security roles.
    AccessProfile.FIELD_MANAGER: frozenset(
        {"FIELD_MANAGER", "TECHNICIAN", "ACP_EMPLOYEE_MOBILE", "DISPATCHER"}
    ),
}


@dataclass(frozen=True)
class MatchCandidate:
    employee_id: UUID
    source_system: str | None
    source_employee_id: str | None


@dataclass(frozen=True)
class MatchResult:
    outcome: MatchOutcome
    candidates: tuple[MatchCandidate, ...]


def normalize_phone(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        raise SimpleOnboardingConflict("Phone must contain ten digits.")
    return f"+1{digits}"


class SimpleEmployeeOnboardingService:
    @staticmethod
    def _require_authority(context: AuthorizationContext) -> None:
        if not context.has_permission(
            AdministrationPermission.IDENTITY_ONBOARDING_MANAGE
        ):
            raise SimpleOnboardingConflict("Employee onboarding authority is required.")

    async def match(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        branch_id: UUID,
        first_name: str,
        last_name: str,
        email: str,
        phone: str | None,
    ) -> MatchResult:
        self._require_authority(context)
        if not context.can_access_branch(branch_id):
            raise SimpleOnboardingConflict("Branch is not authorized.")
        normalized_email = normalize_email(email)
        normalized_phone = normalize_phone(phone)
        first, last = first_name.strip().casefold(), last_name.strip().casefold()
        if not first or not last:
            raise SimpleOnboardingConflict("Employee name is required.")

        employees = tuple(
            await session.scalars(
                select(Employee).where(
                    Employee.company_id == context.company.id,
                    Employee.home_branch_id == branch_id,
                    Employee.archived_at.is_(None),
                    Employee.termination_date.is_(None),
                )
            )
        )
        candidates: dict[UUID, MatchCandidate] = {}
        source_candidates: dict[str, set[UUID]] = {}
        owner_source_ids = {
            person.source_employee_id
            for person in REAL_ALL_COUNTY_ROSTER
            if person.admission is not RealRosterAdmission.HISTORICAL_TERMINATED
            and person.owner_login_email
            and normalize_email(person.owner_login_email) == normalized_email
            and person.display_name.casefold() == f"{first} {last}"
        }
        for employee in employees:
            if (
                employee.first_name.strip().casefold() != first
                or employee.last_name.strip().casefold() != last
                or await employee_is_synthetic(session, employee=employee)
            ):
                continue
            if employee.status == "active" and employee.membership_id:
                login = await session.scalar(
                    select(User.normalized_email)
                    .join(Membership, Membership.user_id == User.id)
                    .where(
                        Membership.company_id == context.company.id,
                        Membership.id == employee.membership_id,
                        Membership.status.in_(("active", "invited")),
                    )
                )
                if login == normalized_email and (
                    normalized_phone is None or employee.phone == normalized_phone
                ):
                    candidates[employee.id] = MatchCandidate(employee.id, None, None)
                continue
            if employee.status != "inactive" or employee.membership_id is not None:
                continue
            source = await session.scalar(
                select(HcpEmployeeSourceCrosswalk)
                .where(
                    HcpEmployeeSourceCrosswalk.company_id == context.company.id,
                    HcpEmployeeSourceCrosswalk.branch_id == branch_id,
                    HcpEmployeeSourceCrosswalk.employee_id == employee.id,
                    HcpEmployeeSourceCrosswalk.native_employee_id.in_(owner_source_ids),
                    HcpEmployeeSourceCrosswalk.disposition
                    == "CREATE_ENTERPRISE_EMPLOYEE_CANDIDATE",
                )
                .order_by(HcpEmployeeSourceCrosswalk.evidence_version.desc())
                .limit(1)
            )
            if source is not None:
                candidates[employee.id] = MatchCandidate(
                    employee.id, "HOUSECALL_PRO", source.native_employee_id
                )
                source_candidates.setdefault(source.native_employee_id, set()).add(employee.id)

        # A source identity may have several historical crosswalk revisions.  Only
        # the employee named by the newest authoritative revision is a deterministic
        # match; stale revisions must not turn the owner flow into an ambiguity list.
        for native_employee_id, employee_ids in source_candidates.items():
            if len(employee_ids) < 2:
                continue
            latest = await session.scalar(
                select(HcpEmployeeSourceCrosswalk)
                .where(
                    HcpEmployeeSourceCrosswalk.company_id == context.company.id,
                    HcpEmployeeSourceCrosswalk.branch_id == branch_id,
                    HcpEmployeeSourceCrosswalk.native_employee_id == native_employee_id,
                    HcpEmployeeSourceCrosswalk.disposition
                    == "CREATE_ENTERPRISE_EMPLOYEE_CANDIDATE",
                )
                .order_by(HcpEmployeeSourceCrosswalk.evidence_version.desc())
                .limit(1)
            )
            if latest is None or latest.employee_id not in employee_ids:
                continue
            for employee_id in employee_ids - {latest.employee_id}:
                candidates.pop(employee_id, None)
        values = tuple(
            sorted(candidates.values(), key=lambda item: str(item.employee_id))
        )
        return MatchResult(
            MatchOutcome.NONE
            if not values
            else MatchOutcome.SINGLE
            if len(values) == 1
            else MatchOutcome.AMBIGUOUS,
            values,
        )

    async def onboard(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        request_key: str,
        branch_id: UUID,
        first_name: str,
        last_name: str,
        email: str,
        phone: str | None,
        access_profile: AccessProfile,
    ) -> IdentityOnboardingRequest:
        match = await self.match(
            session,
            context=context,
            branch_id=branch_id,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
        )
        if match.outcome is MatchOutcome.AMBIGUOUS:
            raise SimpleOnboardingConflict("Employee identity is ambiguous.")
        role_codes = ROLE_CODES[access_profile]
        roles = tuple(
            await session.scalars(
                select(Role).where(
                    Role.company_id == context.company.id,
                    Role.code.in_(role_codes),
                    Role.status == "active",
                    Role.archived_at.is_(None),
                )
            )
        )
        if {item.code for item in roles} != set(role_codes):
            raise SimpleOnboardingConflict("Access profile is unavailable.")
        branch = await session.scalar(
            select(Branch).where(
                Branch.company_id == context.company.id,
                Branch.id == branch_id,
                Branch.status == "active",
                Branch.archived_at.is_(None),
            )
        )
        if branch is None:
            raise SimpleOnboardingConflict("Active Branch was not found.")
        existing_employee_id = (
            match.candidates[0].employee_id
            if match.outcome is MatchOutcome.SINGLE
            else None
        )
        await session.rollback()
        return await identity_onboarding_service.initiate(
            session,
            context=context,
            command=OnboardingCommand(
                request_key=request_key,
                branch_id=branch_id,
                first_name=first_name,
                last_name=last_name,
                display_name=f"{first_name.strip()} {last_name.strip()}",
                employee_type="employee",
                employee_number_prefix="EMP-",
                employee_number_width=4,
                role_ids=tuple(sorted((item.id for item in roles), key=str)),
                login_email=email,
                existing_employee_id=existing_employee_id,
                phone=normalize_phone(phone),
            ),
        )


simple_employee_onboarding_service = SimpleEmployeeOnboardingService()
