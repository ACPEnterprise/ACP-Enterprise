from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
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
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, ExcludeConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PriceBookCategory(Base):
    __tablename__ = "price_book_categories"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "parent_id"],
            ["price_book_categories.company_id", "price_book_categories.id"],
            name="fk_price_book_category_parent",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('active','archived')", name="ck_price_book_categories_status"
        ),
        CheckConstraint("version >= 1", name="ck_price_book_categories_version"),
        UniqueConstraint("company_id", "code", name="uq_price_book_categories_code"),
        UniqueConstraint(
            "company_id", "id", name="uq_price_book_categories_company_id"
        ),
        Index("ix_price_book_categories_list", "company_id", "status", "name"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    parent_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class PriceBookTaxClassification(Base):
    __tablename__ = "price_book_tax_classifications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','inactive','archived')",
            name="ck_price_book_tax_status",
        ),
        CheckConstraint("version >= 1", name="ck_price_book_tax_version"),
        UniqueConstraint("company_id", "code", name="uq_price_book_tax_code"),
        UniqueConstraint("company_id", "id", name="uq_price_book_tax_company_id"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    taxable: Mapped[bool] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class PriceBookServiceItem(Base):
    __tablename__ = "price_book_service_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_price_book_item_branch",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "category_id"],
            ["price_book_categories.company_id", "price_book_categories.id"],
            name="fk_price_book_item_category",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "current_version_id"],
            ["price_book_price_versions.company_id", "price_book_price_versions.id"],
            name="fk_price_book_item_current_version",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        CheckConstraint(
            "status IN ('draft','active','inactive','archived')",
            name="ck_price_book_items_status",
        ),
        CheckConstraint("version >= 1", name="ck_price_book_items_version"),
        UniqueConstraint("company_id", "code", name="uq_price_book_items_code"),
        UniqueConstraint("company_id", "id", name="uq_price_book_items_company_id"),
        Index(
            "ix_price_book_items_catalog",
            "company_id",
            "branch_id",
            "status",
            "category_id",
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
    category_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    customer_description: Mapped[str] = mapped_column(Text, nullable=False)
    internal_description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    current_version_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class PriceBookPriceVersion(Base):
    __tablename__ = "price_book_price_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "service_item_id"],
            ["price_book_service_items.company_id", "price_book_service_items.id"],
            name="fk_price_book_version_item",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_price_book_version_branch",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "tax_classification_id"],
            [
                "price_book_tax_classifications.company_id",
                "price_book_tax_classifications.id",
            ],
            name="fk_price_book_version_tax",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('draft','active','inactive','superseded','archived')",
            name="ck_price_book_versions_status",
        ),
        CheckConstraint("unit_price >= 0", name="ck_price_book_versions_price"),
        CheckConstraint("version >= 1", name="ck_price_book_versions_version"),
        CheckConstraint(
            "expires_at IS NULL OR expires_at > effective_at",
            name="ck_price_book_versions_window",
        ),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name="ck_price_book_versions_currency"
        ),
        UniqueConstraint(
            "company_id",
            "service_item_id",
            "revision",
            name="uq_price_book_versions_revision",
        ),
        UniqueConstraint("company_id", "id", name="uq_price_book_versions_company_id"),
        Index(
            "ix_price_book_versions_selection",
            "company_id",
            "service_item_id",
            "branch_id",
            "status",
            "effective_at",
            "expires_at",
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
    service_item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    tax_classification_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    rounding_mode: Mapped[str] = mapped_column(
        String(40), nullable=False, default="ROUND_HALF_EVEN"
    )
    activation_reason: Mapped[str | None] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    activated_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


PriceBookPriceVersion.__table__.append_constraint(  # type: ignore[attr-defined]
    ExcludeConstraint(
        (PriceBookPriceVersion.company_id, "="),
        (PriceBookPriceVersion.service_item_id, "="),
        (
            func.coalesce(
                PriceBookPriceVersion.branch_id,
                text("'00000000-0000-0000-0000-000000000000'::uuid"),
            ),
            "=",
        ),
        (
            func.tstzrange(
                PriceBookPriceVersion.effective_at,
                PriceBookPriceVersion.expires_at,
                "[)",
            ),
            "&&",
        ),
        where=text("status = 'active'"),
        using="gist",
        name="ex_price_book_active_windows",
        deferrable=True,
        initially="DEFERRED",
    )
)


class PriceBookComponent(Base):
    __tablename__ = "price_book_components"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "price_version_id"],
            ["price_book_price_versions.company_id", "price_book_price_versions.id"],
            name="fk_price_book_component_version",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "component_type IN ('labor','material')",
            name="ck_price_book_components_type",
        ),
        CheckConstraint("quantity > 0", name="ck_price_book_components_quantity"),
        CheckConstraint(
            "unit_cost IS NULL OR unit_cost >= 0", name="ck_price_book_components_cost"
        ),
        UniqueConstraint(
            "company_id",
            "price_version_id",
            "position",
            name="uq_price_book_components_position",
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
    price_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    component_type: Mapped[str] = mapped_column(String(20), nullable=False)
    code: Mapped[str | None] = mapped_column(String(100))
    label: Mapped[str] = mapped_column(String(240), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class PriceBookOptionGroup(Base):
    __tablename__ = "price_book_option_groups"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','archived')", name="ck_price_book_option_groups_status"
        ),
        CheckConstraint(
            "minimum_selections >= 0 AND maximum_selections >= 1 "
            "AND minimum_selections <= maximum_selections",
            name="ck_price_book_option_groups_selection_bounds",
        ),
        UniqueConstraint("company_id", "code", name="uq_price_book_option_groups_code"),
        UniqueConstraint(
            "company_id", "id", name="uq_price_book_option_groups_company_id"
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
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    minimum_selections: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    maximum_selections: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class PriceBookOption(Base):
    __tablename__ = "price_book_options"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "option_group_id"],
            ["price_book_option_groups.company_id", "price_book_option_groups.id"],
            name="fk_price_book_option_group",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "service_item_id"],
            ["price_book_service_items.company_id", "price_book_service_items.id"],
            name="fk_price_book_option_item",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "option_group_id",
            "position",
            name="uq_price_book_options_position",
        ),
        UniqueConstraint(
            "company_id",
            "option_group_id",
            "service_item_id",
            name="uq_price_book_options_item",
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
    option_group_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    service_item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class PriceBookCommercialSnapshot(Base):
    __tablename__ = "price_book_commercial_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "service_item_id"],
            ["price_book_service_items.company_id", "price_book_service_items.id"],
            name="fk_price_book_snapshot_item",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "price_version_id"],
            ["price_book_price_versions.company_id", "price_book_price_versions.id"],
            name="fk_price_book_snapshot_version",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_price_book_snapshot_branch",
            ondelete="RESTRICT",
        ),
        CheckConstraint("quantity > 0", name="ck_price_book_snapshots_quantity"),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name="ck_price_book_snapshots_currency"
        ),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_price_book_snapshots_idempotency"
        ),
        UniqueConstraint("company_id", "id", name="uq_price_book_snapshots_company_id"),
        Index("ix_price_book_snapshots_digest", "company_id", "digest"),
        Index(
            "ix_price_book_snapshots_lookup",
            "company_id",
            "service_item_id",
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
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    service_item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    price_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    extended_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    snapshot_data: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class PriceBookAuditEntry(Base):
    __tablename__ = "price_book_audit_entries"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_price_book_audit_version"),
        Index(
            "ix_price_book_audit_entity",
            "company_id",
            "entity_type",
            "entity_id",
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
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    prior_state: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    new_state: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class PriceBookReviewBatch(Base):
    __tablename__ = "price_book_review_batches"
    __table_args__ = (
        CheckConstraint(
            "review_type IN ('commercial_content','candidate_prices','tax_classification','membership','source_conflict')",
            name="ck_price_book_review_batches_type",
        ),
        CheckConstraint(
            "status IN ('draft','approved','returned','excluded')",
            name="ck_price_book_review_batches_status",
        ),
        CheckConstraint("version >= 1", name="ck_price_book_review_batches_version"),
        CheckConstraint(
            "candidate_set_digest ~ '^[0-9a-f]{64}$'",
            name="ck_price_book_review_batches_digest",
        ),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_price_book_review_batches_key"
        ),
        UniqueConstraint(
            "company_id", "id", name="uq_price_book_review_batches_company_id"
        ),
        Index(
            "ix_price_book_review_batches_queue",
            "company_id",
            "status",
            "review_type",
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
    configuration_version: Mapped[str] = mapped_column(String(120), nullable=False)
    review_type: Mapped[str] = mapped_column(String(40), nullable=False)
    selector: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    service_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    exclusions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    candidate_set_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    decision_reason: Mapped[str | None] = mapped_column(String(500))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    decided_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class PriceBookAdjustmentProposal(Base):
    __tablename__ = "price_book_adjustment_proposals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','approved','returned','rejected','superseded')",
            name="ck_price_book_adjustment_proposals_status",
        ),
        CheckConstraint(
            "transformation_kind IN ('percentage','fixed_amount','markup_policy')",
            name="ck_price_book_adjustment_proposals_kind",
        ),
        CheckConstraint("version >= 1", name="ck_price_book_adjustment_proposals_version"),
        CheckConstraint(
            "proposal_digest ~ '^[0-9a-f]{64}$'",
            name="ck_price_book_adjustment_proposals_digest",
        ),
        UniqueConstraint(
            "company_id", "recommendation_identity", name="uq_price_book_adjustment_recommendation"
        ),
        UniqueConstraint(
            "company_id", "id", name="uq_price_book_adjustment_proposals_company_id"
        ),
        Index(
            "ix_price_book_adjustment_proposals_queue",
            "company_id",
            "status",
            "created_at",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )
    source_price_book_version: Mapped[str] = mapped_column(String(120), nullable=False)
    recommendation_identity: Mapped[str] = mapped_column(String(160), nullable=False)
    economics_evidence_version: Mapped[str | None] = mapped_column(String(160))
    model_version: Mapped[str | None] = mapped_column(String(160))
    affected_service_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    owner_exclusions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    transformation_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    transformation: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    impacts: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    limitations: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    proposal_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    approved_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
