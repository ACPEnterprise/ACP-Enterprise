"""Persistence models for generic Finance/Economics policy authority."""

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
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


class CompanyFinancePolicyVersion(Base):
    __tablename__ = "economics_company_policy_versions"
    __table_args__ = (
        CheckConstraint("policy_version >= 1", name="ck_eco_policy_version"),
        CheckConstraint(
            "lifecycle IN ('draft','approved','superseded','retired')",
            name="ck_eco_policy_lifecycle",
        ),
        CheckConstraint(
            "disposition IN ('selected','deferred')",
            name="ck_eco_policy_disposition",
        ),
        CheckConstraint(
            "effective_end IS NULL OR effective_end > effective_start",
            name="ck_eco_policy_interval",
        ),
        CheckConstraint("branch_id IS NULL", name="ck_eco_policy_company_scope_v1"),
        UniqueConstraint(
            "company_id",
            "family_key",
            "policy_version",
            name="uq_eco_policy_family_version",
        ),
        UniqueConstraint("company_id", "id", name="uq_eco_policy_company_id"),
        Index(
            "ix_eco_policy_resolution",
            "company_id",
            "family_key",
            "lifecycle",
            "effective_start",
            "effective_end",
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
    family_key: Mapped[str] = mapped_column(String(100), nullable=False)
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    strategy_key: Mapped[str | None] = mapped_column(String(100))
    disposition: Mapped[str] = mapped_column(String(20), nullable=False)
    parameters: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    evidence_acceptance_rule_refs: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    effective_start: Mapped[date] = mapped_column(Date, nullable=False)
    effective_end: Mapped[date | None] = mapped_column(Date)
    lifecycle: Mapped[str] = mapped_column(String(20), nullable=False)
    definition_version: Mapped[str] = mapped_column(String(80), nullable=False)
    decision_evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    supersedes_policy_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("economics_company_policy_versions.id", ondelete="RESTRICT"),
    )
    drafted_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    approved_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    audit_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class FinancePolicySnapshotRecord(Base):
    __tablename__ = "economics_policy_snapshots"
    __table_args__ = (
        CheckConstraint("branch_id IS NULL", name="ck_eco_snapshot_company_scope_v1"),
        UniqueConstraint(
            "company_id", "snapshot_digest", name="uq_eco_snapshot_digest"
        ),
        Index("ix_eco_snapshot_replay", "company_id", "subject_identity", "as_of_date"),
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
    subject_identity: Mapped[str] = mapped_column(String(200), nullable=False)
    reconciliation_key: Mapped[str] = mapped_column(String(240), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    policy_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    policy_digests: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    deferred_family_keys: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    parameter_gap_digests: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    definition_version: Mapped[str] = mapped_column(String(80), nullable=False)
    snapshot_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CompanyFinancePolicyParameter(Base):
    __tablename__ = "economics_company_policy_parameters"
    __table_args__ = (
        CheckConstraint("parameter_version >= 1", name="ck_eco_parameter_version"),
        CheckConstraint("branch_id IS NULL", name="ck_eco_parameter_company_scope_v1"),
        CheckConstraint(
            "effective_end IS NULL OR effective_end > effective_start",
            name="ck_eco_parameter_interval",
        ),
        UniqueConstraint(
            "company_id",
            "family_key",
            "parameter_key",
            "parameter_version",
            name="uq_eco_parameter_version",
        ),
        Index(
            "ix_eco_parameter_resolution",
            "company_id",
            "family_key",
            "parameter_key",
            "effective_start",
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
    family_key: Mapped[str] = mapped_column(String(100), nullable=False)
    parameter_key: Mapped[str] = mapped_column(String(100), nullable=False)
    parameter_version: Mapped[int] = mapped_column(Integer, nullable=False)
    value: Mapped[object] = mapped_column(JSONB, nullable=False)
    effective_start: Mapped[date] = mapped_column(Date, nullable=False)
    effective_end: Mapped[date | None] = mapped_column(Date)
    definition_version: Mapped[str] = mapped_column(String(80), nullable=False)
    parameter_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CompanyFinancePolicyGap(Base):
    __tablename__ = "economics_company_policy_gaps"
    __table_args__ = (
        CheckConstraint("branch_id IS NULL", name="ck_eco_policy_gap_company_scope_v1"),
        CheckConstraint(
            "state IN ('unresolved','resolved')", name="ck_eco_policy_gap_state"
        ),
        UniqueConstraint(
            "company_id",
            "family_key",
            "gap_key",
            "effective_start",
            name="uq_eco_policy_gap_identity",
        ),
        Index("ix_eco_policy_gap_open", "company_id", "family_key", "state"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    branch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    family_key: Mapped[str] = mapped_column(String(100), nullable=False)
    gap_key: Mapped[str] = mapped_column(String(120), nullable=False)
    requirement: Mapped[str] = mapped_column(Text, nullable=False)
    authority_dependency: Mapped[str] = mapped_column(String(200), nullable=False)
    effective_start: Mapped[date] = mapped_column(Date, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    decision_evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    gap_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    registered_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
