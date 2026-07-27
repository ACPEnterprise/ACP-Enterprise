from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
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
    source_id_sha256: Mapped[str | None] = mapped_column(String(64))
    disposition: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
