from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


CODE_PATTERN = r"^[a-z][a-z0-9_.-]{0,63}$"
LANGUAGE_CODE_PATTERN = r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$"
LIFECYCLE_CHECK = "status IN ('active', 'inactive')"
TECHNICAL_PROFICIENCY_CHECK = (
    "proficiency IN ('awareness', 'assisted', 'qualified', 'advanced', 'expert')"
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorkforceCapabilityProfile(Base):
    __tablename__ = "workforce_capability_profiles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "employee_id"],
            ["employees.company_id", "employees.id"],
            name="fk_workforce_profiles_employee",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id", "employee_id", name="uq_workforce_profiles_company_employee"
        ),
        UniqueConstraint("company_id", "id", name="uq_workforce_profiles_company_id"),
        CheckConstraint(LIFECYCLE_CHECK, name="ck_workforce_profiles_status"),
        CheckConstraint(
            "concurrency_version >= 1", name="ck_workforce_profiles_version"
        ),
        Index("ix_workforce_profiles_company_status", "company_id", "status", "id"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "companies.id", name="fk_workforce_profiles_company", ondelete="RESTRICT"
        ),
        nullable=False,
    )
    employee_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    concurrency_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class CapabilityCategory(Base):
    __tablename__ = "workforce_capability_categories"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "code", name="uq_workforce_capability_categories_company_code"
        ),
        UniqueConstraint(
            "company_id", "id", name="uq_workforce_capability_categories_company_id"
        ),
        CheckConstraint(
            f"code ~ '{CODE_PATTERN}'", name="ck_workforce_capability_categories_code"
        ),
        CheckConstraint(
            "length(btrim(display_name)) > 0",
            name="ck_workforce_capability_categories_name",
        ),
        CheckConstraint(
            LIFECYCLE_CHECK, name="ck_workforce_capability_categories_status"
        ),
        CheckConstraint(
            "concurrency_version >= 1",
            name="ck_workforce_capability_categories_version",
        ),
        Index(
            "ix_workforce_capability_categories_company_status",
            "company_id",
            "status",
            "code",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "companies.id",
            name="fk_workforce_capability_categories_company",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    concurrency_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class Capability(Base):
    __tablename__ = "workforce_capabilities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "category_id"],
            [
                "workforce_capability_categories.company_id",
                "workforce_capability_categories.id",
            ],
            name="fk_workforce_capabilities_category",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id", "code", name="uq_workforce_capabilities_company_code"
        ),
        UniqueConstraint(
            "company_id", "id", name="uq_workforce_capabilities_company_id"
        ),
        CheckConstraint(
            f"code ~ '{CODE_PATTERN}'", name="ck_workforce_capabilities_code"
        ),
        CheckConstraint(
            "length(btrim(display_name)) > 0", name="ck_workforce_capabilities_name"
        ),
        CheckConstraint(LIFECYCLE_CHECK, name="ck_workforce_capabilities_status"),
        CheckConstraint(
            "concurrency_version >= 1", name="ck_workforce_capabilities_version"
        ),
        Index(
            "ix_workforce_capabilities_company_category",
            "company_id",
            "category_id",
            "status",
            "code",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    category_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    concurrency_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class WorkforceCapability(Base):
    __tablename__ = "workforce_profile_capabilities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "profile_id"],
            [
                "workforce_capability_profiles.company_id",
                "workforce_capability_profiles.id",
            ],
            name="fk_workforce_profile_capabilities_profile",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "capability_id"],
            ["workforce_capabilities.company_id", "workforce_capabilities.id"],
            name="fk_workforce_profile_capabilities_capability",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "profile_id",
            "capability_id",
            name="uq_workforce_profile_capabilities_profile_capability",
        ),
        CheckConstraint(
            TECHNICAL_PROFICIENCY_CHECK,
            name="ck_workforce_profile_capabilities_level",
        ),
        CheckConstraint(
            LIFECYCLE_CHECK, name="ck_workforce_profile_capabilities_status"
        ),
        CheckConstraint(
            "concurrency_version >= 1",
            name="ck_workforce_profile_capabilities_version",
        ),
        Index(
            "ix_workforce_profile_capabilities_company_capability",
            "company_id",
            "capability_id",
            "status",
            "profile_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    profile_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    capability_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    proficiency: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    concurrency_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class Certification(Base):
    __tablename__ = "workforce_certifications"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "code", name="uq_workforce_certifications_company_code"
        ),
        UniqueConstraint(
            "company_id", "id", name="uq_workforce_certifications_company_id"
        ),
        CheckConstraint(
            f"code ~ '{CODE_PATTERN}'", name="ck_workforce_certifications_code"
        ),
        CheckConstraint(
            "length(btrim(display_name)) > 0", name="ck_workforce_certifications_name"
        ),
        CheckConstraint(LIFECYCLE_CHECK, name="ck_workforce_certifications_status"),
        CheckConstraint(
            "concurrency_version >= 1", name="ck_workforce_certifications_version"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "companies.id",
            name="fk_workforce_certifications_company",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    issuing_authority: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    concurrency_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class WorkforceCertification(Base):
    __tablename__ = "workforce_profile_certifications"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "profile_id"],
            [
                "workforce_capability_profiles.company_id",
                "workforce_capability_profiles.id",
            ],
            name="fk_workforce_profile_certifications_profile",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "certification_id"],
            ["workforce_certifications.company_id", "workforce_certifications.id"],
            name="fk_workforce_profile_certifications_certification",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "profile_id",
            "certification_id",
            "credential_reference",
            name="uq_workforce_profile_certifications_credential",
        ),
        CheckConstraint(
            "status IN ('pending', 'active', 'suspended', 'expired', 'revoked')",
            name="ck_workforce_profile_certifications_status",
        ),
        CheckConstraint(
            "expires_on IS NULL OR issued_on IS NULL OR expires_on >= issued_on",
            name="ck_workforce_profile_certifications_dates",
        ),
        CheckConstraint(
            "(verified_at IS NULL) = (verified_by_user_id IS NULL)",
            name="ck_workforce_profile_certifications_verification",
        ),
        CheckConstraint(
            "concurrency_version >= 1",
            name="ck_workforce_profile_certifications_version",
        ),
        Index(
            "ix_workforce_profile_certifications_company_status",
            "company_id",
            "status",
            "expires_on",
            "profile_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    profile_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    certification_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    credential_reference: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    issued_on: Mapped[date | None] = mapped_column(Date)
    expires_on: Mapped[date | None] = mapped_column(Date)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_workforce_profile_certifications_verified_by",
            ondelete="RESTRICT",
        ),
    )
    concurrency_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class EquipmentCapability(Base):
    __tablename__ = "workforce_equipment_capabilities"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "code", name="uq_workforce_equipment_company_code"
        ),
        UniqueConstraint("company_id", "id", name="uq_workforce_equipment_company_id"),
        CheckConstraint(f"code ~ '{CODE_PATTERN}'", name="ck_workforce_equipment_code"),
        CheckConstraint(
            "length(btrim(display_name)) > 0", name="ck_workforce_equipment_name"
        ),
        CheckConstraint(LIFECYCLE_CHECK, name="ck_workforce_equipment_status"),
        CheckConstraint(
            "concurrency_version >= 1", name="ck_workforce_equipment_version"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "companies.id",
            name="fk_workforce_equipment_company",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    concurrency_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class WorkforceEquipmentCapability(Base):
    __tablename__ = "workforce_profile_equipment_capabilities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "profile_id"],
            [
                "workforce_capability_profiles.company_id",
                "workforce_capability_profiles.id",
            ],
            name="fk_workforce_profile_equipment_profile",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "equipment_capability_id"],
            [
                "workforce_equipment_capabilities.company_id",
                "workforce_equipment_capabilities.id",
            ],
            name="fk_workforce_profile_equipment_capability",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "profile_id",
            "equipment_capability_id",
            name="uq_workforce_profile_equipment_profile_capability",
        ),
        CheckConstraint(
            TECHNICAL_PROFICIENCY_CHECK,
            name="ck_workforce_profile_equipment_level",
        ),
        CheckConstraint(LIFECYCLE_CHECK, name="ck_workforce_profile_equipment_status"),
        CheckConstraint(
            "concurrency_version >= 1", name="ck_workforce_profile_equipment_version"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    profile_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    equipment_capability_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    proficiency: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    concurrency_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class WorkforceBranchEligibility(Base):
    __tablename__ = "workforce_branch_eligibilities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "profile_id"],
            [
                "workforce_capability_profiles.company_id",
                "workforce_capability_profiles.id",
            ],
            name="fk_workforce_branch_eligibilities_profile",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_workforce_branch_eligibilities_branch",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "profile_id",
            "branch_id",
            name="uq_workforce_branch_eligibilities_profile_branch",
        ),
        CheckConstraint(
            LIFECYCLE_CHECK, name="ck_workforce_branch_eligibilities_status"
        ),
        CheckConstraint(
            "ends_on IS NULL OR starts_on IS NULL OR ends_on >= starts_on",
            name="ck_workforce_branch_eligibilities_dates",
        ),
        CheckConstraint(
            "concurrency_version >= 1",
            name="ck_workforce_branch_eligibilities_version",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    profile_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    starts_on: Mapped[date | None] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date)
    concurrency_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class WorkforceGeographicCoverage(Base):
    __tablename__ = "workforce_geographic_coverages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "profile_id"],
            [
                "workforce_capability_profiles.company_id",
                "workforce_capability_profiles.id",
            ],
            name="fk_workforce_geographic_coverages_profile",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "profile_id",
            "coverage_type",
            "coverage_code",
            name="uq_workforce_geographic_coverages_profile_type_code",
        ),
        CheckConstraint(
            "coverage_type IN ('postal_code', 'territory')",
            name="ck_workforce_geographic_coverages_type",
        ),
        CheckConstraint(
            "coverage_code ~ '^[A-Za-z0-9][A-Za-z0-9 .-]{0,31}$'",
            name="ck_workforce_geographic_coverages_code",
        ),
        CheckConstraint(
            LIFECYCLE_CHECK, name="ck_workforce_geographic_coverages_status"
        ),
        CheckConstraint(
            "concurrency_version >= 1",
            name="ck_workforce_geographic_coverages_version",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    profile_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    coverage_type: Mapped[str] = mapped_column(String(20), nullable=False)
    coverage_code: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    concurrency_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class WorkRestriction(Base):
    __tablename__ = "workforce_work_restrictions"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "code", name="uq_workforce_work_restrictions_company_code"
        ),
        UniqueConstraint(
            "company_id", "id", name="uq_workforce_work_restrictions_company_id"
        ),
        CheckConstraint(
            f"code ~ '{CODE_PATTERN}'", name="ck_workforce_work_restrictions_code"
        ),
        CheckConstraint(
            "length(btrim(display_name)) > 0",
            name="ck_workforce_work_restrictions_name",
        ),
        CheckConstraint(LIFECYCLE_CHECK, name="ck_workforce_work_restrictions_status"),
        CheckConstraint(
            "concurrency_version >= 1",
            name="ck_workforce_work_restrictions_version",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "companies.id",
            name="fk_workforce_work_restrictions_company",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    concurrency_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class WorkforceWorkRestriction(Base):
    __tablename__ = "workforce_profile_work_restrictions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "profile_id"],
            [
                "workforce_capability_profiles.company_id",
                "workforce_capability_profiles.id",
            ],
            name="fk_workforce_profile_restrictions_profile",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "restriction_id"],
            [
                "workforce_work_restrictions.company_id",
                "workforce_work_restrictions.id",
            ],
            name="fk_workforce_profile_restrictions_definition",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "profile_id",
            "restriction_id",
            "starts_on",
            name="uq_workforce_profile_restrictions_profile_definition_start",
        ),
        CheckConstraint(
            LIFECYCLE_CHECK, name="ck_workforce_profile_restrictions_status"
        ),
        CheckConstraint(
            "ends_on IS NULL OR starts_on IS NULL OR ends_on >= starts_on",
            name="ck_workforce_profile_restrictions_dates",
        ),
        CheckConstraint(
            "concurrency_version >= 1",
            name="ck_workforce_profile_restrictions_version",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    profile_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    restriction_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    starts_on: Mapped[date | None] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date)
    operational_note: Mapped[str | None] = mapped_column(String(500))
    concurrency_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class Language(Base):
    __tablename__ = "workforce_languages"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "code", name="uq_workforce_languages_company_code"
        ),
        UniqueConstraint("company_id", "id", name="uq_workforce_languages_company_id"),
        CheckConstraint(
            f"code ~ '{LANGUAGE_CODE_PATTERN}'", name="ck_workforce_languages_code"
        ),
        CheckConstraint(
            "length(btrim(english_name)) > 0",
            name="ck_workforce_languages_english_name",
        ),
        CheckConstraint(LIFECYCLE_CHECK, name="ck_workforce_languages_status"),
        CheckConstraint(
            "concurrency_version >= 1", name="ck_workforce_languages_version"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "companies.id", name="fk_workforce_languages_company", ondelete="RESTRICT"
        ),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(35), nullable=False)
    english_name: Mapped[str] = mapped_column(String(120), nullable=False)
    native_name: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    concurrency_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class WorkforceLanguageCapability(Base):
    __tablename__ = "workforce_language_capabilities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "profile_id"],
            [
                "workforce_capability_profiles.company_id",
                "workforce_capability_profiles.id",
            ],
            name="fk_workforce_language_capabilities_profile",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "language_id"],
            ["workforce_languages.company_id", "workforce_languages.id"],
            name="fk_workforce_language_capabilities_language",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "profile_id",
            "language_id",
            name="uq_workforce_language_capabilities_profile_language",
        ),
        CheckConstraint(
            "spoken_proficiency IN ('basic', 'conversational', 'professional', 'fluent', 'native')",
            name="ck_workforce_language_capabilities_spoken",
        ),
        CheckConstraint(
            "reading_proficiency IS NULL OR reading_proficiency IN ('basic', 'conversational', 'professional', 'fluent', 'native')",
            name="ck_workforce_language_capabilities_reading",
        ),
        CheckConstraint(
            "writing_proficiency IS NULL OR writing_proficiency IN ('basic', 'conversational', 'professional', 'fluent', 'native')",
            name="ck_workforce_language_capabilities_writing",
        ),
        CheckConstraint(
            "NOT interpreter_verified OR interpreter_verified_at IS NOT NULL",
            name="ck_workforce_language_capabilities_interpreter",
        ),
        CheckConstraint(
            LIFECYCLE_CHECK, name="ck_workforce_language_capabilities_status"
        ),
        CheckConstraint(
            "concurrency_version >= 1",
            name="ck_workforce_language_capabilities_version",
        ),
        Index(
            "ix_workforce_language_capabilities_company_language",
            "company_id",
            "language_id",
            "status",
            "profile_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    profile_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    language_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    spoken_proficiency: Mapped[str] = mapped_column(String(20), nullable=False)
    reading_proficiency: Mapped[str | None] = mapped_column(String(20))
    writing_proficiency: Mapped[str | None] = mapped_column(String(20))
    customer_facing_eligible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    interpreter_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    interpreter_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    concurrency_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
