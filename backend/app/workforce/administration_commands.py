from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.audit.service import AuditEntry, audit_service
from app.platform.employees.models import Employee
from app.platform.permissions.authorization import AuthorizationContext
from app.workforce.models import (
    Capability,
    Certification,
    Language,
    WorkforceCapability,
    WorkforceCapabilityProfile,
    WorkforceCertification,
    WorkforceLanguageCapability,
    WorkforceWorkingAvailability,
)


class WorkforceAdministrationConflict(ValueError):
    pass


class WorkforceAdministrationService:
    async def ensure_profile(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        employee_id: UUID,
    ) -> tuple[WorkforceCapabilityProfile, bool]:
        async with session.begin():
            employee = await self._employee(session, context, employee_id)
            profile = await session.scalar(
                select(WorkforceCapabilityProfile).where(
                    WorkforceCapabilityProfile.company_id == context.company.id,
                    WorkforceCapabilityProfile.employee_id == employee.id,
                )
            )
            created = profile is None
            if profile is None:
                profile = WorkforceCapabilityProfile(
                    company_id=context.company.id,
                    employee_id=employee.id,
                    status="active",
                )
                session.add(profile)
                await session.flush()
                self._audit(
                    session,
                    context,
                    "workforce.profile_created",
                    profile.id,
                    {"employee_id": str(employee.id)},
                )
        return profile, created

    async def add_capability(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        employee_id: UUID,
        capability_id: UUID,
        proficiency: str,
    ) -> tuple[UUID, bool]:
        async with session.begin():
            profile = await self._profile(session, context, employee_id)
            capability = await session.scalar(
                select(Capability).where(
                    Capability.company_id == context.company.id,
                    Capability.id == capability_id,
                    Capability.status == "active",
                )
            )
            if capability is None:
                raise WorkforceAdministrationConflict("Capability was not found.")
            existing = await session.scalar(
                select(WorkforceCapability)
                .where(
                    WorkforceCapability.company_id == context.company.id,
                    WorkforceCapability.profile_id == profile.id,
                    WorkforceCapability.capability_id == capability.id,
                )
                .with_for_update()
            )
            if existing:
                if existing.proficiency != proficiency or existing.status != "active":
                    raise WorkforceAdministrationConflict(
                        "Capability evidence conflicts with current authority."
                    )
                return existing.id, False
            evidence = WorkforceCapability(
                company_id=context.company.id,
                profile_id=profile.id,
                capability_id=capability.id,
                proficiency=proficiency,
            )
            session.add(evidence)
            await session.flush()
            self._audit(session, context, "workforce.capability_recorded", evidence.id)
        return evidence.id, True

    async def add_certification(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        employee_id: UUID,
        certification_id: UUID,
        credential_reference: str,
        status: str,
        issued_on: date | None,
        expires_on: date | None,
    ) -> tuple[UUID, bool]:
        async with session.begin():
            profile = await self._profile(session, context, employee_id)
            definition = await session.scalar(
                select(Certification).where(
                    Certification.company_id == context.company.id,
                    Certification.id == certification_id,
                    Certification.status == "active",
                )
            )
            if definition is None:
                raise WorkforceAdministrationConflict("Certification was not found.")
            existing = await session.scalar(
                select(WorkforceCertification)
                .where(
                    WorkforceCertification.company_id == context.company.id,
                    WorkforceCertification.profile_id == profile.id,
                    WorkforceCertification.certification_id == definition.id,
                    WorkforceCertification.credential_reference
                    == credential_reference.strip(),
                )
                .with_for_update()
            )
            requested = (status, issued_on, expires_on)
            if existing:
                if (existing.status, existing.issued_on, existing.expires_on) != requested:
                    raise WorkforceAdministrationConflict(
                        "Certification evidence conflicts with current authority."
                    )
                return existing.id, False
            evidence = WorkforceCertification(
                company_id=context.company.id,
                profile_id=profile.id,
                certification_id=definition.id,
                credential_reference=credential_reference.strip(),
                status=status,
                issued_on=issued_on,
                expires_on=expires_on,
            )
            session.add(evidence)
            await session.flush()
            self._audit(session, context, "workforce.certification_recorded", evidence.id)
        return evidence.id, True

    async def add_language(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        employee_id: UUID,
        language_id: UUID,
        spoken_proficiency: str,
        customer_facing_eligible: bool,
    ) -> tuple[UUID, bool]:
        async with session.begin():
            profile = await self._profile(session, context, employee_id)
            language = await session.scalar(
                select(Language).where(
                    Language.company_id == context.company.id,
                    Language.id == language_id,
                    Language.status == "active",
                )
            )
            if language is None:
                raise WorkforceAdministrationConflict("Language was not found.")
            existing = await session.scalar(
                select(WorkforceLanguageCapability)
                .where(
                    WorkforceLanguageCapability.company_id == context.company.id,
                    WorkforceLanguageCapability.profile_id == profile.id,
                    WorkforceLanguageCapability.language_id == language.id,
                )
                .with_for_update()
            )
            if existing:
                if (
                    existing.spoken_proficiency != spoken_proficiency
                    or existing.customer_facing_eligible != customer_facing_eligible
                    or existing.status != "active"
                ):
                    raise WorkforceAdministrationConflict(
                        "Language evidence conflicts with current authority."
                    )
                return existing.id, False
            evidence = WorkforceLanguageCapability(
                company_id=context.company.id,
                profile_id=profile.id,
                language_id=language.id,
                spoken_proficiency=spoken_proficiency,
                customer_facing_eligible=customer_facing_eligible,
            )
            session.add(evidence)
            await session.flush()
            self._audit(session, context, "workforce.language_recorded", evidence.id)
        return evidence.id, True

    async def add_availability(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        employee_id: UUID,
        branch_id: UUID,
        start_at: datetime,
        end_at: datetime,
        status: str,
        source: str,
    ) -> tuple[UUID, bool]:
        if not context.can_access_branch(branch_id):
            raise WorkforceAdministrationConflict("Branch is not authorized.")
        async with session.begin():
            profile = await self._profile(session, context, employee_id)
            existing = await session.scalar(
                select(WorkforceWorkingAvailability)
                .where(
                    WorkforceWorkingAvailability.company_id == context.company.id,
                    WorkforceWorkingAvailability.profile_id == profile.id,
                    WorkforceWorkingAvailability.branch_id == branch_id,
                    WorkforceWorkingAvailability.start_at == start_at,
                    WorkforceWorkingAvailability.end_at == end_at,
                )
                .with_for_update()
            )
            if existing:
                if existing.status != status or existing.source != source:
                    raise WorkforceAdministrationConflict(
                        "Availability evidence conflicts with current authority."
                    )
                return existing.id, False
            evidence = WorkforceWorkingAvailability(
                company_id=context.company.id,
                profile_id=profile.id,
                branch_id=branch_id,
                start_at=start_at,
                end_at=end_at,
                status=status,
                source=source,
            )
            session.add(evidence)
            await session.flush()
            self._audit(session, context, "workforce.availability_recorded", evidence.id)
        return evidence.id, True

    @staticmethod
    async def _employee(
        session: AsyncSession, context: AuthorizationContext, employee_id: UUID
    ) -> Employee:
        employee = await session.scalar(
            select(Employee)
            .where(
                Employee.company_id == context.company.id,
                Employee.id == employee_id,
            )
            .with_for_update()
        )
        if employee is None or (
            employee.home_branch_id is not None
            and not context.can_access_branch(employee.home_branch_id)
        ):
            raise WorkforceAdministrationConflict("Employee was not found.")
        return employee

    async def _profile(
        self, session: AsyncSession, context: AuthorizationContext, employee_id: UUID
    ) -> WorkforceCapabilityProfile:
        await self._employee(session, context, employee_id)
        profile = await session.scalar(
            select(WorkforceCapabilityProfile)
            .where(
                WorkforceCapabilityProfile.company_id == context.company.id,
                WorkforceCapabilityProfile.employee_id == employee_id,
                WorkforceCapabilityProfile.status == "active",
            )
            .with_for_update()
        )
        if profile is None:
            raise WorkforceAdministrationConflict("Workforce profile is required.")
        return profile

    @staticmethod
    def _audit(
        session: AsyncSession,
        context: AuthorizationContext,
        action: str,
        resource_id: UUID,
        details: dict[str, object] | None = None,
    ) -> None:
        audit_service.stage(
            session,
            AuditEntry(
                action=action,
                resource_type="workforce_evidence",
                resource_id=resource_id,
                actor_user_id=context.user.id,
                company_id=context.company.id,
                branch_id=context.active_branch.id if context.active_branch else None,
                details=details or {},
            ),
        )


workforce_administration_service = WorkforceAdministrationService()
