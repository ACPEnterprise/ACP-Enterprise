from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
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


class LuminaryFindingRecord(Base):
    __tablename__ = "luminary_findings"
    __table_args__ = (
        CheckConstraint(
            "length(finding_digest) = 64", name="ck_luminary_finding_digest"
        ),
        CheckConstraint(
            "period_end >= period_start", name="ck_luminary_finding_period"
        ),
        CheckConstraint(
            "confidence_percent between 0 and 100",
            name="ck_luminary_finding_confidence",
        ),
        CheckConstraint(
            "lifecycle in ('accepted','voided')", name="ck_luminary_finding_lifecycle"
        ),
        UniqueConstraint(
            "company_id", "finding_identity", name="uq_luminary_finding_identity"
        ),
        UniqueConstraint("company_id", "id", name="uq_luminary_finding_company_id"),
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_luminary_finding_company_branch",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "supersedes_finding_id"],
            ["luminary_findings.company_id", "luminary_findings.id"],
            name="fk_luminary_finding_company_supersedes",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_luminary_finding_scope_period",
            "company_id",
            "branch_id",
            "period_start",
            "period_end",
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
    branch_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True)
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    finding_class: Mapped[str] = mapped_column(String(40), nullable=False)
    finding_type: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    observations: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    evidence: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    evidence_package_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence_percent: Mapped[int] = mapped_column(nullable=False)
    completeness: Mapped[str] = mapped_column(String(30), nullable=False)
    freshness: Mapped[str] = mapped_column(String(30), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    limitations: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    investigate_next: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    engine_version: Mapped[str] = mapped_column(String(100), nullable=False)
    definition_version: Mapped[str] = mapped_column(String(100), nullable=False)
    finding_identity: Mapped[str] = mapped_column(String(100), nullable=False)
    finding_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    lifecycle: Mapped[str] = mapped_column(
        String(20), nullable=False, default="accepted"
    )
    supersedes_finding_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True)
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class LuminaryBriefingRecord(Base):
    __tablename__ = "luminary_briefings"
    __table_args__ = (
        CheckConstraint(
            "length(briefing_digest) = 64", name="ck_luminary_briefing_digest"
        ),
        CheckConstraint(
            "period_end >= period_start", name="ck_luminary_briefing_period"
        ),
        UniqueConstraint(
            "company_id", "briefing_identity", name="uq_luminary_briefing_identity"
        ),
        UniqueConstraint("company_id", "id", name="uq_luminary_briefing_company_id"),
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_luminary_briefing_company_branch",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "supersedes_briefing_id"],
            ["luminary_briefings.company_id", "luminary_briefings.id"],
            name="fk_luminary_briefing_company_supersedes",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_luminary_briefing_scope_period",
            "company_id",
            "branch_id",
            "period_start",
            "period_end",
            "created_at",
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
    branch_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True)
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    evidence_package_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    finding_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    finding_digests: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    sections: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    completeness: Mapped[str] = mapped_column(String(30), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    engine_version: Mapped[str] = mapped_column(String(100), nullable=False)
    definition_version: Mapped[str] = mapped_column(String(100), nullable=False)
    briefing_identity: Mapped[str] = mapped_column(String(100), nullable=False)
    briefing_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    supersedes_briefing_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True)
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
