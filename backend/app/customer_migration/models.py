from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
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


class CustomerMigrationSourceArtifact(Base):
    __tablename__ = "customer_migration_source_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "branch_id",
            "source_system",
            "source_sha256",
            name="uq_customer_migration_source_artifact",
        ),
        CheckConstraint("byte_size >= 0", name="ck_customer_source_artifact_size"),
        CheckConstraint("row_count >= 0", name="ck_customer_source_artifact_rows"),
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
    source_system: Mapped[str] = mapped_column(String(50), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(100), nullable=False)
    transformation_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CustomerMigrationStagingRun(Base):
    __tablename__ = "customer_migration_staging_runs"
    __table_args__ = (
        CheckConstraint(
            "customers_proposed >= 0 AND contacts_proposed >= 0 "
            "AND service_locations_proposed >= 0 "
            "AND billing_addresses_proposed >= 0 AND child_exception_count >= 0 "
            "AND unmapped_field_count >= 0",
            name="ck_customer_staging_run_counts_nonnegative",
        ),
    )

    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customer_migration_runs.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    artifact_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customer_migration_source_artifacts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reused_staging: Mapped[bool] = mapped_column(Boolean, nullable=False)
    customers_proposed: Mapped[int] = mapped_column(Integer, nullable=False)
    contacts_proposed: Mapped[int] = mapped_column(Integer, nullable=False)
    service_locations_proposed: Mapped[int] = mapped_column(Integer, nullable=False)
    billing_addresses_proposed: Mapped[int] = mapped_column(Integer, nullable=False)
    child_exception_count: Mapped[int] = mapped_column(Integer, nullable=False)
    unmapped_field_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CustomerMigrationSourceRow(Base):
    __tablename__ = "customer_migration_source_rows"
    __table_args__ = (
        CheckConstraint("row_number >= 2", name="ck_customer_source_row_number"),
        CheckConstraint(
            "disposition IN ('accepted', 'rejected', 'duplicate')",
            name="ck_customer_source_row_disposition",
        ),
        UniqueConstraint(
            "artifact_id", "row_number", name="uq_customer_source_row_artifact_row"
        ),
        Index(
            "ix_customer_source_rows_artifact_disposition",
            "artifact_id",
            "disposition",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    artifact_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customer_migration_source_artifacts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_identity: Mapped[str | None] = mapped_column(String(191))
    source_id_sha256: Mapped[str | None] = mapped_column(String(64))
    source_row_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    disposition: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CustomerMigrationCandidate(Base):
    __tablename__ = "customer_migration_candidates"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('customer', 'contact', 'service_location', "
            "'billing_address')",
            name="ck_customer_migration_candidate_entity",
        ),
        CheckConstraint("ordinal >= 0", name="ck_customer_candidate_ordinal"),
        UniqueConstraint(
            "source_row_id",
            "entity_type",
            "ordinal",
            name="uq_customer_candidate_source_entity_ordinal",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    source_row_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customer_migration_source_rows.id", ondelete="RESTRICT"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CustomerMigrationEvidence(Base):
    __tablename__ = "customer_migration_evidence"
    __table_args__ = (
        CheckConstraint(
            "evidence_type IN ('unmapped_field', 'incomplete_address_group')",
            name="ck_customer_migration_evidence_type",
        ),
        UniqueConstraint(
            "source_row_id",
            "evidence_type",
            "evidence_key",
            name="uq_customer_migration_evidence_source_key",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    source_row_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customer_migration_source_rows.id", ondelete="RESTRICT"),
        nullable=False,
    )
    evidence_type: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence_key: Mapped[str] = mapped_column(String(191), nullable=False)
    evidence_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CustomerMigrationChildException(Base):
    __tablename__ = "customer_migration_child_exceptions"
    __table_args__ = (
        UniqueConstraint(
            "source_row_id",
            "reason_code",
            "address_group_number",
            name="uq_customer_child_exception_source_group",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    source_row_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customer_migration_source_rows.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_id_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(100), nullable=False)
    address_group_number: Mapped[int] = mapped_column(Integer, nullable=False)
    missing_fields: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    evidence_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
