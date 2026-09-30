from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class QboNativeApplicationRecord(Base):
    """Append-only disposition for one acquired QBO record revision."""

    __tablename__ = "qbo_native_application_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "disposition IN ('APPLIED','BOUND','QUARANTINED',"
            "'PROVIDER_UNAVAILABLE','UNSUPPORTED','REJECTED_WITH_REASON')",
            name="ck_qbo_application_disposition",
        ),
        CheckConstraint("version >= 1", name="ck_qbo_application_version"),
        CheckConstraint(
            "length(source_digest) = 64 AND length(evidence_digest) = 64",
            name="ck_qbo_application_digests",
        ),
        CheckConstraint(
            "(disposition IN ('APPLIED','BOUND')) = (native_id IS NOT NULL)",
            name="ck_qbo_application_native_result",
        ),
        UniqueConstraint(
            "company_id",
            "realm_id",
            "source_family",
            "provider_record_id",
            "version",
            name="uq_qbo_application_record_version",
        ),
        Index(
            "uq_qbo_application_record_current",
            "company_id",
            "realm_id",
            "source_family",
            "provider_record_id",
            unique=True,
            postgresql_where=text("superseded_at IS NULL"),
        ),
        Index(
            "ix_qbo_application_company_family_disposition",
            "company_id",
            "source_family",
            "disposition",
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
    branch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    realm_id: Mapped[str] = mapped_column(String(160), nullable=False)
    source_family: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_record_id: Mapped[str] = mapped_column(String(191), nullable=False)
    provider_version: Mapped[str | None] = mapped_column(String(80))
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disposition: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    native_type: Mapped[str | None] = mapped_column(String(80))
    native_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    deterministic_match_basis: Mapped[str | None] = mapped_column(String(120))
    dependency_identities: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    display_evidence: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    applied_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QboNativeReviewItem(Base):
    """Human-readable review queue card for one quarantined QBO record."""

    __tablename__ = "qbo_native_review_items"
    __table_args__ = (
        CheckConstraint(
            "state IN ('OPEN','RESOLVED','IGNORED','REJECTED')",
            name="ck_qbo_review_state",
        ),
        UniqueConstraint("application_record_id", name="uq_qbo_review_application"),
        Index("ix_qbo_review_company_state", "company_id", "state", "source_family"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    application_record_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("qbo_native_application_records.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_family: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_record_id: Mapped[str] = mapped_column(String(191), nullable=False)
    reference_number: Mapped[str | None] = mapped_column(String(160))
    source_date: Mapped[str | None] = mapped_column(String(40))
    source_amount: Mapped[str | None] = mapped_column(String(80))
    source_entity_names: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    candidate_native_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    conflicting_fields: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    exact_conflict: Mapped[str] = mapped_column(Text, nullable=False)
    affected_dependents: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    allowed_actions: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="OPEN")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)
