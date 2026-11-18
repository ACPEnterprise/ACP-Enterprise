"""Durable, Company-scoped migration-factory evidence."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
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


class MigrationFactoryRunRecord(Base):
    __tablename__ = "migration_factory_runs"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "id", name="uq_migration_factory_run_company_id"
        ),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_migration_factory_run_replay"
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
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    factory_version: Mapped[str] = mapped_column(String(80), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class MigrationProviderAuthorizationRecord(Base):
    """Digest-protected grant history; token material remains in secret storage."""

    __tablename__ = "migration_factory_provider_authorizations"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "provider",
            "authorization_digest",
            name="uq_migration_provider_authorization",
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
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_company_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    authorized_scopes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    token_reference: Mapped[str] = mapped_column(String(191), nullable=False)
    authorization_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    supersedes_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("migration_factory_provider_authorizations.id", ondelete="RESTRICT"),
    )


class MigrationCoverageRecord(Base):
    __tablename__ = "migration_factory_coverage"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    domain: Mapped[str] = mapped_column(String(48), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    methods: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    source_systems: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    source_count: Mapped[int | None] = mapped_column(Integer)
    received_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quarantined_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    explanation: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    __table_args__ = (
        UniqueConstraint(
            "company_id", "run_id", "domain", name="uq_migration_coverage_domain"
        ),
        ForeignKeyConstraint(
            ["company_id", "run_id"],
            ["migration_factory_runs.company_id", "migration_factory_runs.id"],
            ondelete="RESTRICT",
        ),
    )


class MigrationRawEvidenceRecord(Base):
    __tablename__ = "migration_factory_raw_evidence"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "source_system",
            "object_type",
            "object_id",
            "evidence_digest",
            name="uq_migration_raw_evidence",
        ),
        UniqueConstraint("company_id", "id", name="uq_migration_raw_company_id"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    object_type: Mapped[str] = mapped_column(String(80), nullable=False)
    object_id: Mapped[str] = mapped_column(String(191), nullable=False)
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    payload_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    api_version: Mapped[str] = mapped_column(String(80), nullable=False)
    authority: Mapped[str] = mapped_column(String(120), nullable=False)
    batch_identity: Mapped[str] = mapped_column(String(160), nullable=False)
    page_identity: Mapped[str] = mapped_column(String(160), nullable=False)


class MigrationPageCheckpointRecord(Base):
    __tablename__ = "migration_factory_page_checkpoints"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "run_id",
            "source_system",
            "family",
            "page_identity",
            name="uq_migration_page_checkpoint",
        ),
        ForeignKeyConstraint(
            ["company_id", "run_id"],
            ["migration_factory_runs.company_id", "migration_factory_runs.id"],
            ondelete="RESTRICT",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    family: Mapped[str] = mapped_column(String(80), nullable=False)
    page_identity: Mapped[str] = mapped_column(String(160), nullable=False)
    high_water_mark: Mapped[str | None] = mapped_column(String(191))
    received_count: Mapped[int] = mapped_column(Integer, nullable=False)
    quarantined_count: Mapped[int] = mapped_column(Integer, nullable=False)
    terminal_page: Mapped[bool] = mapped_column(Boolean, nullable=False)
    response_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class MigrationAuthorityRuleRecord(Base):
    __tablename__ = "migration_factory_authority_rules"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "domain",
            "field_name",
            "version",
            name="uq_migration_authority_rule_version",
        ),
        UniqueConstraint("rule_digest", name="uq_migration_authority_rule_digest"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    domain: Mapped[str] = mapped_column(String(48), nullable=False)
    field_name: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_precedence: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    rule_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class MigrationCertificateRecord(Base):
    __tablename__ = "migration_factory_certificates"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "certificate_digest", name="uq_migration_certificate_digest"
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
    run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    coverage: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    source_hashes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    transformation_version: Mapped[str] = mapped_column(String(80), nullable=False)
    conflicts: Mapped[int] = mapped_column(Integer, nullable=False)
    unresolved_exceptions: Mapped[int] = mapped_column(Integer, nullable=False)
    zero_silent_drops: Mapped[bool] = mapped_column(Boolean, nullable=False)
    certificate_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    certified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class MigrationDeltaCursorRecord(Base):
    __tablename__ = "migration_factory_delta_cursors"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "source_system", name="uq_migration_delta_cursor"
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
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    high_water_mark: Mapped[str] = mapped_column(String(191), nullable=False)
    webhook_sequence: Mapped[str | None] = mapped_column(String(191))
    reconciliation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
