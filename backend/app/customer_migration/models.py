from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CustomerMigrationRun(Base):
    __tablename__ = "customer_migration_runs"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('dry_run', 'import')", name="ck_customer_migration_runs_mode"
        ),
        CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_customer_migration_runs_status",
        ),
        CheckConstraint(
            "source_count >= 0 AND accepted_count >= 0 AND rejected_count >= 0 "
            "AND duplicate_count >= 0 AND unresolved_count >= 0",
            name="ck_customer_migration_runs_counts_nonnegative",
        ),
        CheckConstraint(
            "source_count = accepted_count + rejected_count + duplicate_count "
            "+ unresolved_count",
            name="ck_customer_migration_runs_counts_reconcile",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    branch_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="RESTRICT"),
        nullable=False,
    )
    initiated_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(String(50), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unresolved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CustomerSourceIdentity(Base):
    __tablename__ = "customer_source_identities"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "source_system",
            "source_customer_id",
            name="uq_customer_source_identity",
        ),
        UniqueConstraint(
            "company_id",
            "source_system",
            "customer_id",
            name="uq_customer_source_target",
        ),
        UniqueConstraint(
            "id", "company_id", name="uq_customer_source_identities_id_company"
        ),
        UniqueConstraint(
            "id",
            "company_id",
            "customer_id",
            name="uq_customer_source_identities_parent_scope",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    branch_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="RESTRICT"),
        nullable=False,
    )
    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(String(50), nullable=False)
    source_customer_id: Mapped[str] = mapped_column(String(191), nullable=False)
    first_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customer_migration_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CustomerMigrationException(Base):
    __tablename__ = "customer_migration_exceptions"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('customer', 'contact', 'service_location')",
            name="ck_customer_migration_exceptions_entity_type",
        ),
        CheckConstraint(
            "disposition IN ('rejected', 'duplicate', 'unresolved')",
            name="ck_customer_migration_exceptions_disposition",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customer_migration_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    entity_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="customer"
    )
    source_id_sha256: Mapped[str | None] = mapped_column(String(64))
    disposition: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CustomerContactSourceIdentity(Base):
    __tablename__ = "customer_contact_source_identities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["customer_source_identity_id", "company_id", "customer_id"],
            [
                "customer_source_identities.id",
                "customer_source_identities.company_id",
                "customer_source_identities.customer_id",
            ],
            name="fk_contact_source_identity_customer_company",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["contact_id", "customer_id"],
            ["customer_contacts.id", "customer_contacts.customer_id"],
            name="fk_contact_source_identity_contact_customer",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "source_system",
            "source_contact_id",
            name="uq_customer_contact_source_identity",
        ),
        UniqueConstraint(
            "company_id",
            "source_system",
            "contact_id",
            name="uq_customer_contact_source_target",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    customer_source_identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    contact_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(String(50), nullable=False)
    source_contact_id: Mapped[str] = mapped_column(String(191), nullable=False)
    first_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customer_migration_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ServiceLocationSourceIdentity(Base):
    __tablename__ = "service_location_source_identities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["customer_source_identity_id", "company_id", "customer_id"],
            [
                "customer_source_identities.id",
                "customer_source_identities.company_id",
                "customer_source_identities.customer_id",
            ],
            name="fk_location_source_identity_customer_company",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["service_location_id", "customer_id"],
            ["service_locations.id", "service_locations.customer_id"],
            name="fk_location_source_identity_location_customer",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "source_system",
            "source_location_id",
            name="uq_service_location_source_identity",
        ),
        UniqueConstraint(
            "company_id",
            "source_system",
            "service_location_id",
            name="uq_service_location_source_target",
        ),
        UniqueConstraint(
            "id",
            "company_id",
            "customer_id",
            "service_location_id",
            name="uq_service_location_source_parent_scope",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    customer_source_identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    service_location_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(String(50), nullable=False)
    source_location_id: Mapped[str] = mapped_column(String(191), nullable=False)
    first_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customer_migration_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CustomerMigrationProgress(Base):
    __tablename__ = "customer_migration_progress"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('customer', 'contact', 'service_location')",
            name="ck_customer_migration_progress_entity_type",
        ),
        CheckConstraint(
            "source_count >= 0 AND processed_count >= 0 "
            "AND accepted_count >= 0 AND rejected_count >= 0 "
            "AND duplicate_count >= 0 AND unresolved_count >= 0",
            name="ck_customer_migration_progress_counts_nonnegative",
        ),
        CheckConstraint(
            "processed_count = accepted_count + rejected_count + duplicate_count "
            "+ unresolved_count AND processed_count <= source_count",
            name="ck_customer_migration_progress_counts_reconcile",
        ),
        UniqueConstraint(
            "run_id", "entity_type", name="uq_customer_migration_progress_entity"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customer_migration_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False)
    processed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    unresolved_count: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
