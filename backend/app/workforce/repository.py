from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.workforce.models import (
    Capability,
    CapabilityCategory,
    Certification,
    EquipmentCapability,
    Language,
    WorkforceBranchEligibility,
    WorkforceCapability,
    WorkforceCapabilityProfile,
    WorkforceCertification,
    WorkforceEquipmentCapability,
    WorkforceGeographicCoverage,
    WorkforceLanguageCapability,
    WorkforceWorkRestriction,
    WorkRestriction,
)
from app.workforce.records import (
    WorkforceCapabilityProfileRecord,
    WorkforceCapabilityRecord,
    WorkforceBranchEligibilityRecord,
    WorkforceCertificationRecord,
    WorkforceEquipmentRecord,
    WorkforceGeographicCoverageRecord,
    WorkforceLanguageRecord,
    WorkforceWorkRestrictionRecord,
)


class WorkforceCapabilityRepository:
    """Company-scoped persistence primitives; callers own policy and transactions."""

    @staticmethod
    async def create_profile(
        session: AsyncSession, *, company_id: UUID, employee_id: UUID
    ) -> WorkforceCapabilityProfileRecord:
        profile = WorkforceCapabilityProfile(
            company_id=company_id,
            employee_id=employee_id,
            status="active",
            concurrency_version=1,
        )
        session.add(profile)
        await session.flush()
        return _profile_record(profile)

    @staticmethod
    async def get_profile(
        session: AsyncSession, *, company_id: UUID, profile_id: UUID
    ) -> WorkforceCapabilityProfileRecord | None:
        profile = await session.scalar(
            select(WorkforceCapabilityProfile).where(
                WorkforceCapabilityProfile.company_id == company_id,
                WorkforceCapabilityProfile.id == profile_id,
            )
        )
        return None if profile is None else _profile_record(profile)

    @staticmethod
    async def get_profile_for_update(
        session: AsyncSession, *, company_id: UUID, profile_id: UUID
    ) -> WorkforceCapabilityProfileRecord | None:
        profile = await session.scalar(
            select(WorkforceCapabilityProfile)
            .where(
                WorkforceCapabilityProfile.company_id == company_id,
                WorkforceCapabilityProfile.id == profile_id,
            )
            .with_for_update()
        )
        return None if profile is None else _profile_record(profile)

    @staticmethod
    async def list_profiles(
        session: AsyncSession, *, company_id: UUID
    ) -> tuple[WorkforceCapabilityProfileRecord, ...]:
        profiles = (
            await session.scalars(
                select(WorkforceCapabilityProfile)
                .where(WorkforceCapabilityProfile.company_id == company_id)
                .order_by(
                    WorkforceCapabilityProfile.employee_id,
                    WorkforceCapabilityProfile.id,
                )
            )
        ).all()
        return tuple(_profile_record(profile) for profile in profiles)

    @staticmethod
    async def update_profile_status(
        session: AsyncSession,
        *,
        company_id: UUID,
        profile_id: UUID,
        expected_version: int,
        status: str,
    ) -> WorkforceCapabilityProfileRecord | None:
        profile = await session.scalar(
            update(WorkforceCapabilityProfile)
            .where(
                WorkforceCapabilityProfile.company_id == company_id,
                WorkforceCapabilityProfile.id == profile_id,
                WorkforceCapabilityProfile.concurrency_version == expected_version,
            )
            .values(
                status=status,
                concurrency_version=WorkforceCapabilityProfile.concurrency_version + 1,
            )
            .returning(WorkforceCapabilityProfile)
        )
        return None if profile is None else _profile_record(profile)

    @staticmethod
    async def create_capability_category(
        session: AsyncSession,
        *,
        company_id: UUID,
        code: str,
        display_name: str,
        description: str | None = None,
    ) -> UUID:
        return await _add(
            session,
            CapabilityCategory(
                company_id=company_id,
                code=code,
                display_name=display_name,
                description=description,
            ),
        )

    @staticmethod
    async def create_capability(
        session: AsyncSession,
        *,
        company_id: UUID,
        category_id: UUID,
        code: str,
        display_name: str,
        description: str | None = None,
    ) -> UUID:
        return await _add(
            session,
            Capability(
                company_id=company_id,
                category_id=category_id,
                code=code,
                display_name=display_name,
                description=description,
            ),
        )

    @staticmethod
    async def add_workforce_capability(
        session: AsyncSession,
        *,
        company_id: UUID,
        profile_id: UUID,
        capability_id: UUID,
        proficiency: str,
    ) -> UUID:
        return await _add(
            session,
            WorkforceCapability(
                company_id=company_id,
                profile_id=profile_id,
                capability_id=capability_id,
                proficiency=proficiency,
            ),
        )

    @staticmethod
    async def create_certification(
        session: AsyncSession,
        *,
        company_id: UUID,
        code: str,
        display_name: str,
        issuing_authority: str | None = None,
    ) -> UUID:
        return await _add(
            session,
            Certification(
                company_id=company_id,
                code=code,
                display_name=display_name,
                issuing_authority=issuing_authority,
            ),
        )

    @staticmethod
    async def add_workforce_certification(
        session: AsyncSession,
        *,
        company_id: UUID,
        profile_id: UUID,
        certification_id: UUID,
        credential_reference: str,
        status: str = "pending",
        issued_on: date | None = None,
        expires_on: date | None = None,
    ) -> UUID:
        return await _add(
            session,
            WorkforceCertification(
                company_id=company_id,
                profile_id=profile_id,
                certification_id=certification_id,
                credential_reference=credential_reference,
                status=status,
                issued_on=issued_on,
                expires_on=expires_on,
            ),
        )

    @staticmethod
    async def create_equipment_capability(
        session: AsyncSession,
        *,
        company_id: UUID,
        code: str,
        display_name: str,
    ) -> UUID:
        return await _add(
            session,
            EquipmentCapability(
                company_id=company_id, code=code, display_name=display_name
            ),
        )

    @staticmethod
    async def add_workforce_equipment_capability(
        session: AsyncSession,
        *,
        company_id: UUID,
        profile_id: UUID,
        equipment_capability_id: UUID,
        proficiency: str,
    ) -> UUID:
        return await _add(
            session,
            WorkforceEquipmentCapability(
                company_id=company_id,
                profile_id=profile_id,
                equipment_capability_id=equipment_capability_id,
                proficiency=proficiency,
            ),
        )

    @staticmethod
    async def add_branch_eligibility(
        session: AsyncSession,
        *,
        company_id: UUID,
        profile_id: UUID,
        branch_id: UUID,
        starts_on: date | None = None,
        ends_on: date | None = None,
    ) -> UUID:
        return await _add(
            session,
            WorkforceBranchEligibility(
                company_id=company_id,
                profile_id=profile_id,
                branch_id=branch_id,
                starts_on=starts_on,
                ends_on=ends_on,
            ),
        )

    @staticmethod
    async def add_geographic_coverage(
        session: AsyncSession,
        *,
        company_id: UUID,
        profile_id: UUID,
        coverage_type: str,
        coverage_code: str,
    ) -> UUID:
        return await _add(
            session,
            WorkforceGeographicCoverage(
                company_id=company_id,
                profile_id=profile_id,
                coverage_type=coverage_type,
                coverage_code=coverage_code,
            ),
        )

    @staticmethod
    async def create_work_restriction(
        session: AsyncSession,
        *,
        company_id: UUID,
        code: str,
        display_name: str,
    ) -> UUID:
        return await _add(
            session,
            WorkRestriction(
                company_id=company_id, code=code, display_name=display_name
            ),
        )

    @staticmethod
    async def add_work_restriction(
        session: AsyncSession,
        *,
        company_id: UUID,
        profile_id: UUID,
        restriction_id: UUID,
        starts_on: date | None = None,
        ends_on: date | None = None,
        operational_note: str | None = None,
    ) -> UUID:
        return await _add(
            session,
            WorkforceWorkRestriction(
                company_id=company_id,
                profile_id=profile_id,
                restriction_id=restriction_id,
                starts_on=starts_on,
                ends_on=ends_on,
                operational_note=operational_note,
            ),
        )

    @staticmethod
    async def create_language(
        session: AsyncSession,
        *,
        company_id: UUID,
        code: str,
        english_name: str,
        native_name: str | None = None,
    ) -> UUID:
        return await _add(
            session,
            Language(
                company_id=company_id,
                code=code,
                english_name=english_name,
                native_name=native_name,
            ),
        )

    @staticmethod
    async def add_language_capability(
        session: AsyncSession,
        *,
        company_id: UUID,
        profile_id: UUID,
        language_id: UUID,
        spoken_proficiency: str,
        reading_proficiency: str | None = None,
        writing_proficiency: str | None = None,
        customer_facing_eligible: bool = False,
        interpreter_verified: bool = False,
        interpreter_verified_at: datetime | None = None,
    ) -> UUID:
        return await _add(
            session,
            WorkforceLanguageCapability(
                company_id=company_id,
                profile_id=profile_id,
                language_id=language_id,
                spoken_proficiency=spoken_proficiency,
                reading_proficiency=reading_proficiency,
                writing_proficiency=writing_proficiency,
                customer_facing_eligible=customer_facing_eligible,
                interpreter_verified=interpreter_verified,
                interpreter_verified_at=interpreter_verified_at,
            ),
        )

    @staticmethod
    async def get_complete_profile(
        session: AsyncSession, *, company_id: UUID, profile_id: UUID
    ) -> WorkforceCapabilityProfileRecord | None:
        profile = await session.scalar(
            select(WorkforceCapabilityProfile).where(
                WorkforceCapabilityProfile.company_id == company_id,
                WorkforceCapabilityProfile.id == profile_id,
            )
        )
        if profile is None:
            return None

        capabilities = (
            await session.execute(
                select(WorkforceCapability, Capability)
                .join(
                    Capability,
                    (Capability.company_id == WorkforceCapability.company_id)
                    & (Capability.id == WorkforceCapability.capability_id),
                )
                .where(
                    WorkforceCapability.company_id == company_id,
                    WorkforceCapability.profile_id == profile_id,
                )
                .order_by(Capability.code, Capability.id)
            )
        ).all()
        certifications = (
            await session.execute(
                select(WorkforceCertification, Certification)
                .join(
                    Certification,
                    (Certification.company_id == WorkforceCertification.company_id)
                    & (Certification.id == WorkforceCertification.certification_id),
                )
                .where(
                    WorkforceCertification.company_id == company_id,
                    WorkforceCertification.profile_id == profile_id,
                )
                .order_by(Certification.code, WorkforceCertification.id)
            )
        ).all()
        languages = (
            await session.execute(
                select(WorkforceLanguageCapability, Language)
                .join(
                    Language,
                    (Language.company_id == WorkforceLanguageCapability.company_id)
                    & (Language.id == WorkforceLanguageCapability.language_id),
                )
                .where(
                    WorkforceLanguageCapability.company_id == company_id,
                    WorkforceLanguageCapability.profile_id == profile_id,
                )
                .order_by(Language.code, Language.id)
            )
        ).all()
        equipment = (
            await session.execute(
                select(WorkforceEquipmentCapability, EquipmentCapability)
                .join(
                    EquipmentCapability,
                    (
                        EquipmentCapability.company_id
                        == WorkforceEquipmentCapability.company_id
                    )
                    & (
                        EquipmentCapability.id
                        == WorkforceEquipmentCapability.equipment_capability_id
                    ),
                )
                .where(
                    WorkforceEquipmentCapability.company_id == company_id,
                    WorkforceEquipmentCapability.profile_id == profile_id,
                )
                .order_by(EquipmentCapability.code, EquipmentCapability.id)
            )
        ).all()
        branches = (
            await session.scalars(
                select(WorkforceBranchEligibility)
                .where(
                    WorkforceBranchEligibility.company_id == company_id,
                    WorkforceBranchEligibility.profile_id == profile_id,
                )
                .order_by(
                    WorkforceBranchEligibility.branch_id,
                    WorkforceBranchEligibility.id,
                )
            )
        ).all()
        coverages = (
            await session.scalars(
                select(WorkforceGeographicCoverage)
                .where(
                    WorkforceGeographicCoverage.company_id == company_id,
                    WorkforceGeographicCoverage.profile_id == profile_id,
                )
                .order_by(
                    WorkforceGeographicCoverage.coverage_type,
                    WorkforceGeographicCoverage.coverage_code,
                    WorkforceGeographicCoverage.id,
                )
            )
        ).all()
        restrictions = (
            await session.execute(
                select(WorkforceWorkRestriction, WorkRestriction)
                .join(
                    WorkRestriction,
                    (WorkRestriction.company_id == WorkforceWorkRestriction.company_id)
                    & (WorkRestriction.id == WorkforceWorkRestriction.restriction_id),
                )
                .where(
                    WorkforceWorkRestriction.company_id == company_id,
                    WorkforceWorkRestriction.profile_id == profile_id,
                )
                .order_by(WorkRestriction.code, WorkforceWorkRestriction.id)
            )
        ).all()

        root = _profile_record(profile)
        return WorkforceCapabilityProfileRecord(
            id=root.id,
            company_id=root.company_id,
            employee_id=root.employee_id,
            status=root.status,
            concurrency_version=root.concurrency_version,
            created_at=root.created_at,
            updated_at=root.updated_at,
            capabilities=tuple(
                WorkforceCapabilityRecord(
                    capability_id=definition.id,
                    code=definition.code,
                    display_name=definition.display_name,
                    proficiency=association.proficiency,
                    status=association.status,
                )
                for association, definition in capabilities
            ),
            certifications=tuple(
                WorkforceCertificationRecord(
                    certification_id=definition.id,
                    code=definition.code,
                    display_name=definition.display_name,
                    credential_reference=association.credential_reference,
                    status=association.status,
                    issued_on=association.issued_on,
                    expires_on=association.expires_on,
                )
                for association, definition in certifications
            ),
            equipment_capabilities=tuple(
                WorkforceEquipmentRecord(
                    equipment_capability_id=definition.id,
                    code=definition.code,
                    display_name=definition.display_name,
                    proficiency=association.proficiency,
                    status=association.status,
                )
                for association, definition in equipment
            ),
            branch_eligibilities=tuple(
                WorkforceBranchEligibilityRecord(
                    branch_id=association.branch_id,
                    status=association.status,
                    starts_on=association.starts_on,
                    ends_on=association.ends_on,
                )
                for association in branches
            ),
            geographic_coverages=tuple(
                WorkforceGeographicCoverageRecord(
                    coverage_type=coverage.coverage_type,
                    coverage_code=coverage.coverage_code,
                    status=coverage.status,
                )
                for coverage in coverages
            ),
            work_restrictions=tuple(
                WorkforceWorkRestrictionRecord(
                    restriction_id=definition.id,
                    code=definition.code,
                    display_name=definition.display_name,
                    status=association.status,
                    starts_on=association.starts_on,
                    ends_on=association.ends_on,
                    operational_note=association.operational_note,
                )
                for association, definition in restrictions
            ),
            languages=tuple(
                WorkforceLanguageRecord(
                    language_id=language.id,
                    code=language.code,
                    english_name=language.english_name,
                    native_name=language.native_name,
                    spoken_proficiency=association.spoken_proficiency,
                    reading_proficiency=association.reading_proficiency,
                    writing_proficiency=association.writing_proficiency,
                    customer_facing_eligible=association.customer_facing_eligible,
                    interpreter_verified=association.interpreter_verified,
                    status=association.status,
                )
                for association, language in languages
            ),
        )


def _profile_record(
    profile: WorkforceCapabilityProfile,
) -> WorkforceCapabilityProfileRecord:
    return WorkforceCapabilityProfileRecord(
        id=profile.id,
        company_id=profile.company_id,
        employee_id=profile.employee_id,
        status=profile.status,
        concurrency_version=profile.concurrency_version,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


async def _add(session: AsyncSession, record: object) -> UUID:
    session.add(record)
    await session.flush()
    record_id = getattr(record, "id")
    if not isinstance(record_id, UUID):
        raise TypeError("persisted workforce record did not receive a UUID")
    return record_id


workforce_capability_repository = WorkforceCapabilityRepository()
