from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
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


class EstimateNumberSequence(Base):
    __tablename__ = "estimate_number_sequences"
    __table_args__ = (
        CheckConstraint("last_value >= 0", name="ck_estimate_number_sequences_value"),
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    last_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class Estimate(Base):
    __tablename__ = "estimate_proposals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_estimates_company_branch",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "customer_id"],
            ["customers.company_id", "customers.id"],
            name="fk_estimate_proposals_customer_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["service_location_id", "customer_id"],
            ["service_locations.id", "service_locations.customer_id"],
            name="fk_estimates_customer_location",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "current_revision_id"],
            ["estimate_revisions.company_id", "estimate_revisions.id"],
            name="fk_estimates_current_revision",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        CheckConstraint(
            "estimate_number ~ '^EST-[0-9]{6,}$'", name="ck_estimates_number"
        ),
        CheckConstraint(
            "status IN ('draft','sent','viewed','approved','rejected','expired',"
            "'proposed','accepted','declined','cancelled')",
            name="ck_estimates_status",
        ),
        CheckConstraint(
            "acceptance_status IN ('not_requested','pending','approved','rejected',"
            "'expired','accepted','declined','withdrawn')",
            name="ck_estimates_acceptance_status",
        ),
        CheckConstraint("version >= 1", name="ck_estimates_version"),
        UniqueConstraint(
            "company_id", "estimate_number", name="uq_estimates_company_number"
        ),
        UniqueConstraint("company_id", "id", name="uq_estimate_proposals_company_id"),
        Index(
            "ix_estimates_company_branch_status", "company_id", "branch_id", "status"
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
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    service_location_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    estimate_number: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    acceptance_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="not_requested"
    )
    current_revision_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    updated_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class EstimateRevision(Base):
    __tablename__ = "estimate_revisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "estimate_id"],
            ["estimate_proposals.company_id", "estimate_proposals.id"],
            name="fk_estimate_revisions_estimate",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "parent_revision_id"],
            ["estimate_revisions.company_id", "estimate_revisions.id"],
            name="fk_estimate_revisions_parent",
            ondelete="RESTRICT",
        ),
        CheckConstraint("revision_number >= 1", name="ck_estimate_revisions_number"),
        CheckConstraint(
            "status IN ('draft','issued','superseded','withdrawn')",
            name="ck_estimate_revisions_status",
        ),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name="ck_estimate_revisions_currency"
        ),
        CheckConstraint(
            "subtotal_amount >= 0 AND total_amount >= 0",
            name="ck_estimate_revisions_amounts",
        ),
        CheckConstraint(
            "discount_amount >= 0 AND tax_amount >= 0 AND taxable_basis >= 0",
            name="ck_estimate_revisions_calculation_amounts",
        ),
        CheckConstraint(
            "discount_type IS NULL OR discount_type IN ('fixed','percentage')",
            name="ck_estimate_revisions_discount_type",
        ),
        CheckConstraint(
            "expires_at IS NULL OR expires_at > created_at",
            name="ck_estimate_revisions_expiry",
        ),
        UniqueConstraint(
            "company_id",
            "estimate_id",
            "revision_number",
            name="uq_estimate_revisions_number",
        ),
        UniqueConstraint("company_id", "id", name="uq_estimate_revisions_company_id"),
        Index(
            "ix_estimate_revisions_estimate",
            "company_id",
            "estimate_id",
            "revision_number",
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
    estimate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    parent_revision_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    proposal_title: Mapped[str] = mapped_column(String(240), nullable=False)
    customer_message: Mapped[str | None] = mapped_column(Text)
    terms: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    subtotal_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    discount_type: Mapped[str | None] = mapped_column(String(20))
    discount_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0.00")
    )
    taxable_basis: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0.00")
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0.00")
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    calculation_evidence: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class EstimateLineItem(Base):
    __tablename__ = "estimate_revision_line_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "revision_id"],
            ["estimate_revisions.company_id", "estimate_revisions.id"],
            name="fk_estimate_lines_revision",
            ondelete="RESTRICT",
        ),
        CheckConstraint("position >= 1", name="ck_estimate_lines_position"),
        CheckConstraint(
            "quantity > 0 AND unit_price >= 0 AND line_total >= 0",
            name="ck_estimate_lines_amounts",
        ),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_estimate_lines_currency"),
        UniqueConstraint(
            "company_id", "revision_id", "position", name="uq_estimate_lines_position"
        ),
        UniqueConstraint("company_id", "id", name="uq_estimate_lines_company_id"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    revision_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    discount_allocation: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0.00")
    )
    discounted_basis: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0.00")
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0.00")
    )
    taxable: Mapped[bool] = mapped_column(nullable=False, default=False)
    tax_classification_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    tax_policy_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    tax_policy_version: Mapped[int | None] = mapped_column(Integer)
    applied_rate_basis_points: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class EstimateCommercialSnapshotReference(Base):
    __tablename__ = "estimate_commercial_snapshot_references"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "revision_id"],
            ["estimate_revisions.company_id", "estimate_revisions.id"],
            name="fk_estimate_snapshot_refs_revision",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "line_item_id"],
            [
                "estimate_revision_line_items.company_id",
                "estimate_revision_line_items.id",
            ],
            name="fk_estimate_snapshot_refs_line",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "snapshot_id"],
            [
                "price_book_commercial_snapshots.company_id",
                "price_book_commercial_snapshots.id",
            ],
            name="fk_estimate_snapshot_refs_snapshot",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "snapshot_digest ~ '^[0-9a-f]{64}$'",
            name="ck_estimate_snapshot_refs_digest",
        ),
        UniqueConstraint(
            "company_id", "line_item_id", name="uq_estimate_snapshot_refs_line"
        ),
        UniqueConstraint(
            "company_id",
            "revision_id",
            "snapshot_id",
            name="uq_estimate_snapshot_refs_revision_snapshot",
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
    revision_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    line_item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    snapshot_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    option_group_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    option_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    minimum_selections: Mapped[int | None] = mapped_column(Integer)
    maximum_selections: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class EstimateLifecycleHistory(Base):
    __tablename__ = "estimate_lifecycle_history"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "estimate_id"],
            ["estimate_proposals.company_id", "estimate_proposals.id"],
            name="fk_estimate_history_estimate",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_estimate_history_branch",
            ondelete="RESTRICT",
        ),
        CheckConstraint("version >= 1", name="ck_estimate_history_version"),
        UniqueConstraint(
            "company_id", "estimate_id", "version", name="uq_estimate_history_version"
        ),
        Index(
            "ix_estimate_history_timeline", "company_id", "estimate_id", "occurred_at"
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
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    estimate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(24))
    to_status: Mapped[str] = mapped_column(String(24), nullable=False)
    from_acceptance_status: Mapped[str | None] = mapped_column(String(24))
    to_acceptance_status: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    actor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class EstimateCustomerDecision(Base):
    __tablename__ = "estimate_customer_decisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "estimate_id"],
            ["estimate_proposals.company_id", "estimate_proposals.id"],
            name="fk_estimate_customer_decisions_estimate",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "revision_id"],
            ["estimate_revisions.company_id", "estimate_revisions.id"],
            name="fk_estimate_customer_decisions_revision",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "decision IN ('approved','rejected')",
            name="ck_estimate_customer_decisions_type",
        ),
        CheckConstraint(
            "(decision = 'approved' AND rejection_reason IS NULL) OR "
            "(decision = 'rejected' AND rejection_reason IS NOT NULL "
            "AND length(btrim(rejection_reason)) > 0)",
            name="ck_estimate_customer_decisions_reason",
        ),
        UniqueConstraint(
            "company_id",
            "revision_id",
            name="uq_estimate_customer_decisions_revision",
        ),
        Index(
            "ix_estimate_customer_decisions_estimate",
            "company_id",
            "estimate_id",
            "occurred_at",
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
    estimate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    revision_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    customer_name: Mapped[str] = mapped_column(String(240), nullable=False)
    customer_email: Mapped[str | None] = mapped_column(String(320))
    customer_comment: Mapped[str | None] = mapped_column(Text)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    evidence_reference: Mapped[str | None] = mapped_column(String(240))
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class EstimateJobConversion(Base):
    __tablename__ = "estimate_job_conversions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_estimate_conversions_company_branch",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "estimate_id"],
            ["estimate_proposals.company_id", "estimate_proposals.id"],
            name="fk_estimate_conversions_estimate",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "estimate_revision_id"],
            ["estimate_revisions.company_id", "estimate_revisions.id"],
            name="fk_estimate_conversions_revision",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_estimate_conversions_job",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "estimate_version >= 1", name="ck_estimate_conversions_version"
        ),
        CheckConstraint(
            "snapshot_lineage_digest ~ '^[0-9a-f]{64}$'",
            name="ck_estimate_conversions_digest",
        ),
        CheckConstraint(
            "length(btrim(idempotency_key)) > 0",
            name="ck_estimate_conversions_idempotency_key",
        ),
        UniqueConstraint(
            "company_id", "estimate_id", name="uq_estimate_conversions_estimate"
        ),
        UniqueConstraint("company_id", "job_id", name="uq_estimate_conversions_job"),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_estimate_conversions_idempotency"
        ),
        Index(
            "ix_estimate_conversions_company_branch_time",
            "company_id",
            "branch_id",
            "converted_at",
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
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    estimate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    estimate_revision_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    estimate_version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_lineage: Mapped[list[dict[str, str]]] = mapped_column(JSON, nullable=False)
    snapshot_lineage_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    converted_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    converted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
