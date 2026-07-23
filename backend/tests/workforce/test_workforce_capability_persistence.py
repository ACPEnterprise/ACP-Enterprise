from collections.abc import AsyncIterator
from dataclasses import FrozenInstanceError, dataclass
from datetime import date, datetime, timezone
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.platform.permissions.models  # noqa: F401
from app.core.config import settings
from app.platform.branch.models import Branch
from app.platform.company.models import Company
from app.platform.employees.models import Employee
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
from app.workforce.repository import WorkforceCapabilityRepository


@dataclass(frozen=True)
class WorkforceFixture:
    factory: async_sessionmaker[AsyncSession]
    company_id: UUID
    branch_id: UUID
    employee_id: UUID
    other_company_id: UUID
    other_branch_id: UUID
    other_employee_id: UUID


@pytest_asyncio.fixture
async def workforce_database() -> AsyncIterator[WorkforceFixture]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    company_id, other_company_id = uuid4(), uuid4()
    branch_id, other_branch_id = uuid4(), uuid4()
    employee_id, other_employee_id = uuid4(), uuid4()
    async with factory() as session, session.begin():
        session.add_all(
            [
                Company(
                    id=company_id,
                    name="Workforce Company",
                    code=f"W{uuid4().hex[:8].upper()}",
                    status="active",
                    timezone="America/New_York",
                ),
                Company(
                    id=other_company_id,
                    name="Other Workforce Company",
                    code=f"O{uuid4().hex[:8].upper()}",
                    status="active",
                    timezone="America/New_York",
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                Branch(
                    id=branch_id,
                    company_id=company_id,
                    name="Main",
                    code=f"B{uuid4().hex[:8].upper()}",
                    status="active",
                    timezone="America/New_York",
                    is_primary=True,
                ),
                Branch(
                    id=other_branch_id,
                    company_id=other_company_id,
                    name="Other",
                    code=f"B{uuid4().hex[:8].upper()}",
                    status="active",
                    timezone="America/New_York",
                    is_primary=True,
                ),
                Employee(
                    id=employee_id,
                    company_id=company_id,
                    employee_number="EMP-1",
                    first_name="Avery",
                    last_name="Resource",
                    display_name="Avery Resource",
                    employee_type="employee",
                    status="active",
                ),
                Employee(
                    id=other_employee_id,
                    company_id=other_company_id,
                    employee_number="EMP-2",
                    first_name="Jordan",
                    last_name="Resource",
                    display_name="Jordan Resource",
                    employee_type="employee",
                    status="active",
                ),
            ]
        )
    fixture = WorkforceFixture(
        factory,
        company_id,
        branch_id,
        employee_id,
        other_company_id,
        other_branch_id,
        other_employee_id,
    )
    try:
        yield fixture
    finally:
        async with factory() as session, session.begin():
            for association_model in (
                WorkforceLanguageCapability,
                WorkforceWorkRestriction,
                WorkforceGeographicCoverage,
                WorkforceBranchEligibility,
                WorkforceEquipmentCapability,
                WorkforceCertification,
                WorkforceCapability,
            ):
                await session.execute(
                    delete(association_model).where(
                        association_model.company_id.in_((company_id, other_company_id))
                    )
                )
            await session.execute(
                delete(WorkforceCapabilityProfile).where(
                    WorkforceCapabilityProfile.company_id.in_(
                        (company_id, other_company_id)
                    )
                )
            )
            for catalog_model in (
                Capability,
                CapabilityCategory,
                Certification,
                EquipmentCapability,
                WorkRestriction,
                Language,
            ):
                await session.execute(
                    delete(catalog_model).where(
                        catalog_model.company_id.in_((company_id, other_company_id))
                    )
                )
            await session.execute(
                delete(Employee).where(
                    Employee.id.in_((employee_id, other_employee_id))
                )
            )
            await session.execute(
                delete(Branch).where(Branch.id.in_((branch_id, other_branch_id)))
            )
            await session.execute(
                delete(Company).where(Company.id.in_((company_id, other_company_id)))
            )
        await engine.dispose()


def profile(
    fixture: WorkforceFixture, *, other: bool = False
) -> WorkforceCapabilityProfile:
    return WorkforceCapabilityProfile(
        company_id=fixture.other_company_id if other else fixture.company_id,
        employee_id=fixture.other_employee_id if other else fixture.employee_id,
        status="active",
        concurrency_version=1,
    )


async def persist_profile(fixture: WorkforceFixture) -> WorkforceCapabilityProfile:
    root = profile(fixture)
    async with fixture.factory() as session, session.begin():
        session.add(root)
    return root


@pytest.mark.asyncio
async def test_profile_creation_ownership_and_one_per_employee(
    workforce_database: WorkforceFixture,
) -> None:
    fixture = workforce_database
    async with fixture.factory() as session, session.begin():
        record = await WorkforceCapabilityRepository.create_profile(
            session,
            company_id=fixture.company_id,
            employee_id=fixture.employee_id,
        )
    assert record.company_id == fixture.company_id
    assert record.concurrency_version == 1
    with pytest.raises(FrozenInstanceError):
        record.status = "inactive"  # type: ignore[misc]

    async with fixture.factory() as session:
        session.add(profile(fixture))
        with pytest.raises(IntegrityError):
            await session.commit()
    async with fixture.factory() as session:
        session.add(
            WorkforceCapabilityProfile(
                company_id=fixture.company_id,
                employee_id=fixture.other_employee_id,
                status="active",
                concurrency_version=1,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_capability_catalog_and_association_constraints(
    workforce_database: WorkforceFixture,
) -> None:
    fixture = workforce_database
    root = await persist_profile(fixture)
    category = CapabilityCategory(
        company_id=fixture.company_id,
        code="diagnostics",
        display_name="Diagnostics",
    )
    async with fixture.factory() as session, session.begin():
        session.add(category)
        await session.flush()
        capability = Capability(
            company_id=fixture.company_id,
            category_id=category.id,
            code="diagnostics.sewer",
            display_name="Sewer diagnostics",
        )
        invalid_level_capability = Capability(
            company_id=fixture.company_id,
            category_id=category.id,
            code="diagnostics.other",
            display_name="Other diagnostics",
        )
        session.add_all([capability, invalid_level_capability])
    async with fixture.factory() as session, session.begin():
        session.add(
            WorkforceCapability(
                company_id=fixture.company_id,
                profile_id=root.id,
                capability_id=capability.id,
                proficiency="qualified",
            )
        )
    async with fixture.factory() as session:
        session.add(
            CapabilityCategory(
                company_id=fixture.company_id,
                code="diagnostics",
                display_name="Duplicate",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
    async with fixture.factory() as session:
        session.add(
            WorkforceCapability(
                company_id=fixture.company_id,
                profile_id=root.id,
                capability_id=invalid_level_capability.id,
                proficiency="uncontrolled",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_cross_company_catalog_associations_are_rejected(
    workforce_database: WorkforceFixture,
) -> None:
    fixture = workforce_database
    root = await persist_profile(fixture)
    category = CapabilityCategory(
        company_id=fixture.other_company_id,
        code="other",
        display_name="Other",
    )
    async with fixture.factory() as session, session.begin():
        session.add(category)
        await session.flush()
        capability = Capability(
            company_id=fixture.other_company_id,
            category_id=category.id,
            code="other.skill",
            display_name="Other skill",
        )
        session.add(capability)
    async with fixture.factory() as session:
        session.add(
            WorkforceCapability(
                company_id=fixture.company_id,
                profile_id=root.id,
                capability_id=capability.id,
                proficiency="basic",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_certification_dates_status_and_verification(
    workforce_database: WorkforceFixture,
) -> None:
    fixture = workforce_database
    root = await persist_profile(fixture)
    definition = Certification(
        company_id=fixture.company_id,
        code="trade.license",
        display_name="Trade license",
    )
    async with fixture.factory() as session, session.begin():
        session.add(definition)
    invalid = (
        WorkforceCertification(
            company_id=fixture.company_id,
            profile_id=root.id,
            certification_id=definition.id,
            credential_reference="A",
            status="unknown",
        ),
        WorkforceCertification(
            company_id=fixture.company_id,
            profile_id=root.id,
            certification_id=definition.id,
            credential_reference="B",
            status="active",
            issued_on=date(2027, 1, 1),
            expires_on=date(2026, 1, 1),
        ),
        WorkforceCertification(
            company_id=fixture.company_id,
            profile_id=root.id,
            certification_id=definition.id,
            credential_reference="C",
            status="active",
            verified_at=datetime.now(timezone.utc),
        ),
    )
    for association in invalid:
        async with fixture.factory() as session:
            session.add(association)
            with pytest.raises(IntegrityError):
                await session.commit()


@pytest.mark.asyncio
async def test_equipment_qualification_is_distinct_and_persists(
    workforce_database: WorkforceFixture,
) -> None:
    fixture = workforce_database
    root = await persist_profile(fixture)
    equipment = EquipmentCapability(
        company_id=fixture.company_id,
        code="camera",
        display_name="Camera operation",
    )
    async with fixture.factory() as session, session.begin():
        session.add(equipment)
        await session.flush()
        session.add(
            WorkforceEquipmentCapability(
                company_id=fixture.company_id,
                profile_id=root.id,
                equipment_capability_id=equipment.id,
                proficiency="advanced",
            )
        )


@pytest.mark.asyncio
async def test_branch_eligibility_enforces_company_and_dates(
    workforce_database: WorkforceFixture,
) -> None:
    fixture = workforce_database
    root = await persist_profile(fixture)
    for branch_id, starts_on, ends_on in (
        (fixture.other_branch_id, None, None),
        (fixture.branch_id, date(2027, 1, 1), date(2026, 1, 1)),
    ):
        async with fixture.factory() as session:
            session.add(
                WorkforceBranchEligibility(
                    company_id=fixture.company_id,
                    profile_id=root.id,
                    branch_id=branch_id,
                    starts_on=starts_on,
                    ends_on=ends_on,
                )
            )
            with pytest.raises(IntegrityError):
                await session.commit()


@pytest.mark.asyncio
async def test_geographic_coverage_and_work_restrictions(
    workforce_database: WorkforceFixture,
) -> None:
    fixture = workforce_database
    root = await persist_profile(fixture)
    restriction = WorkRestriction(
        company_id=fixture.company_id,
        code="supervision.required",
        display_name="Supervision required",
    )
    async with fixture.factory() as session, session.begin():
        session.add_all(
            [
                restriction,
                WorkforceGeographicCoverage(
                    company_id=fixture.company_id,
                    profile_id=root.id,
                    coverage_type="postal_code",
                    coverage_code="10001",
                ),
            ]
        )
        await session.flush()
        session.add(
            WorkforceWorkRestriction(
                company_id=fixture.company_id,
                profile_id=root.id,
                restriction_id=restriction.id,
                starts_on=date(2026, 1, 1),
                operational_note="Use approved supervision workflow.",
            )
        )
    async with fixture.factory() as session:
        session.add(
            WorkforceGeographicCoverage(
                company_id=fixture.company_id,
                profile_id=root.id,
                coverage_type="radius",
                coverage_code="10 miles",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_language_catalog_association_and_lifecycle(
    workforce_database: WorkforceFixture,
) -> None:
    fixture = workforce_database
    root = await persist_profile(fixture)
    language = Language(
        company_id=fixture.company_id,
        code="es",
        english_name="Spanish",
        native_name="Español",
        status="inactive",
    )
    async with fixture.factory() as session, session.begin():
        session.add(language)
        await session.flush()
        session.add(
            WorkforceLanguageCapability(
                company_id=fixture.company_id,
                profile_id=root.id,
                language_id=language.id,
                spoken_proficiency="fluent",
                reading_proficiency="professional",
                writing_proficiency="conversational",
                customer_facing_eligible=True,
                interpreter_verified=True,
                interpreter_verified_at=datetime.now(timezone.utc),
                status="inactive",
            )
        )
    async with fixture.factory() as session:
        stored = await session.scalar(
            select(WorkforceLanguageCapability).where(
                WorkforceLanguageCapability.profile_id == root.id
            )
        )
        assert stored is not None
        assert stored.customer_facing_eligible and stored.interpreter_verified
        assert stored.status == "inactive"


@pytest.mark.asyncio
async def test_language_uniqueness_proficiency_and_company_constraints(
    workforce_database: WorkforceFixture,
) -> None:
    fixture = workforce_database
    root = await persist_profile(fixture)
    language = Language(
        company_id=fixture.company_id,
        code="fr",
        english_name="French",
    )
    other_language = Language(
        company_id=fixture.other_company_id,
        code="de",
        english_name="German",
    )
    async with fixture.factory() as session, session.begin():
        session.add_all([language, other_language])
    for association in (
        WorkforceLanguageCapability(
            company_id=fixture.company_id,
            profile_id=root.id,
            language_id=language.id,
            spoken_proficiency="expert",
        ),
        WorkforceLanguageCapability(
            company_id=fixture.company_id,
            profile_id=root.id,
            language_id=other_language.id,
            spoken_proficiency="basic",
        ),
        WorkforceLanguageCapability(
            company_id=fixture.company_id,
            profile_id=root.id,
            language_id=language.id,
            spoken_proficiency="basic",
            interpreter_verified=True,
        ),
    ):
        async with fixture.factory() as session:
            session.add(association)
            with pytest.raises(IntegrityError):
                await session.commit()
    async with fixture.factory() as session:
        session.add_all(
            [
                Language(
                    company_id=fixture.company_id,
                    code="fr",
                    english_name="Duplicate",
                ),
                Language(
                    company_id=fixture.company_id,
                    code="Not valid",
                    english_name="Invalid",
                ),
            ]
        )
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "spoken,reading,writing",
    [
        ("invalid", None, None),
        ("basic", "invalid", None),
        ("basic", None, "invalid"),
    ],
)
async def test_each_language_proficiency_is_constrained(
    spoken: str,
    reading: str | None,
    writing: str | None,
    workforce_database: WorkforceFixture,
) -> None:
    fixture = workforce_database
    root = await persist_profile(fixture)
    language = Language(
        company_id=fixture.company_id,
        code="it",
        english_name="Italian",
    )
    async with fixture.factory() as session, session.begin():
        session.add(language)
    async with fixture.factory() as session:
        session.add(
            WorkforceLanguageCapability(
                company_id=fixture.company_id,
                profile_id=root.id,
                language_id=language.id,
                spoken_proficiency=spoken,
                reading_proficiency=reading,
                writing_proficiency=writing,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_workforce_language_association_is_unique(
    workforce_database: WorkforceFixture,
) -> None:
    fixture = workforce_database
    root = await persist_profile(fixture)
    language = Language(
        company_id=fixture.company_id,
        code="nl",
        english_name="Dutch",
    )
    async with fixture.factory() as session, session.begin():
        session.add(language)
        await session.flush()
        session.add(
            WorkforceLanguageCapability(
                company_id=fixture.company_id,
                profile_id=root.id,
                language_id=language.id,
                spoken_proficiency="basic",
            )
        )
    async with fixture.factory() as session:
        session.add(
            WorkforceLanguageCapability(
                company_id=fixture.company_id,
                profile_id=root.id,
                language_id=language.id,
                spoken_proficiency="fluent",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_repository_ordering_complete_projection_and_concurrency(
    workforce_database: WorkforceFixture,
) -> None:
    fixture = workforce_database
    first = await persist_profile(fixture)
    category = CapabilityCategory(
        company_id=fixture.company_id, code="service", display_name="Service"
    )
    languages = [
        Language(company_id=fixture.company_id, code=code, english_name=code)
        for code in ("es", "en")
    ]
    async with fixture.factory() as session, session.begin():
        session.add(category)
        await session.flush()
        definitions = [
            Capability(
                company_id=fixture.company_id,
                category_id=category.id,
                code=code,
                display_name=code,
            )
            for code in ("zeta", "alpha")
        ]
        session.add_all([*definitions, *languages])
    async with fixture.factory() as session:
        session.add_all(
            [
                *(
                    WorkforceCapability(
                        company_id=fixture.company_id,
                        profile_id=first.id,
                        capability_id=item.id,
                        proficiency="uncontrolled",
                    )
                    for item in definitions
                ),
                *(
                    WorkforceLanguageCapability(
                        company_id=fixture.company_id,
                        profile_id=first.id,
                        language_id=item.id,
                        spoken_proficiency="basic",
                    )
                    for item in languages
                ),
            ]
        )
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()
    # Use valid proficiency values and prove deterministic projections.
    async with fixture.factory() as session, session.begin():
        session.add_all(
            [
                *(
                    WorkforceCapability(
                        company_id=fixture.company_id,
                        profile_id=first.id,
                        capability_id=item.id,
                        proficiency="qualified",
                    )
                    for item in definitions
                ),
                *(
                    WorkforceLanguageCapability(
                        company_id=fixture.company_id,
                        profile_id=first.id,
                        language_id=item.id,
                        spoken_proficiency="basic",
                    )
                    for item in languages
                ),
            ]
        )
    async with fixture.factory() as session, session.begin():
        complete = await WorkforceCapabilityRepository.get_complete_profile(
            session, company_id=fixture.company_id, profile_id=first.id
        )
        assert complete is not None
        assert [item.code for item in complete.capabilities] == ["alpha", "zeta"]
        assert [item.code for item in complete.languages] == ["en", "es"]
        updated = await WorkforceCapabilityRepository.update_profile_status(
            session,
            company_id=fixture.company_id,
            profile_id=first.id,
            expected_version=1,
            status="inactive",
        )
        assert updated is not None and updated.concurrency_version == 2
        stale = await WorkforceCapabilityRepository.update_profile_status(
            session,
            company_id=fixture.company_id,
            profile_id=first.id,
            expected_version=1,
            status="active",
        )
        assert stale is None


@pytest.mark.asyncio
async def test_profile_and_catalog_deletion_is_restricted(
    workforce_database: WorkforceFixture,
) -> None:
    fixture = workforce_database
    root = await persist_profile(fixture)
    language = Language(
        company_id=fixture.company_id,
        code="pt",
        english_name="Portuguese",
    )
    async with fixture.factory() as session, session.begin():
        session.add(language)
        await session.flush()
        session.add(
            WorkforceLanguageCapability(
                company_id=fixture.company_id,
                profile_id=root.id,
                language_id=language.id,
                spoken_proficiency="basic",
            )
        )
    async with fixture.factory() as session:
        await session.delete(await session.get(Language, language.id))
        with pytest.raises(IntegrityError):
            await session.commit()
