"""create price book foundation

Revision ID: q2g4b6d8e053
Revises: p1f3a5c7d942
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "q2g4b6d8e053"
down_revision: str | None = "p1f3a5c7d942"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.create_table(
        "price_book_categories",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("parent_id", UUID),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", UUID, nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "parent_id"],
            ["price_book_categories.company_id", "price_book_categories.id"],
            name="fk_price_book_category_parent",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('active','archived')", name="ck_price_book_categories_status"
        ),
        sa.CheckConstraint("version >= 1", name="ck_price_book_categories_version"),
        sa.UniqueConstraint("company_id", "code", name="uq_price_book_categories_code"),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_price_book_categories_company_id"
        ),
    )
    op.create_index(
        "ix_price_book_categories_list",
        "price_book_categories",
        ["company_id", "status", "name"],
    )
    op.create_table(
        "price_book_tax_classifications",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("taxable", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", UUID, nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "status IN ('active','inactive','archived')",
            name="ck_price_book_tax_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_price_book_tax_version"),
        sa.UniqueConstraint("company_id", "code", name="uq_price_book_tax_code"),
        sa.UniqueConstraint("company_id", "id", name="uq_price_book_tax_company_id"),
    )
    op.create_table(
        "price_book_service_items",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("branch_id", UUID),
        sa.Column("category_id", UUID, nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("customer_description", sa.Text(), nullable=False),
        sa.Column("internal_description", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("current_version_id", UUID),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", UUID, nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_price_book_item_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "category_id"],
            ["price_book_categories.company_id", "price_book_categories.id"],
            name="fk_price_book_item_category",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('draft','active','inactive','archived')",
            name="ck_price_book_items_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_price_book_items_version"),
        sa.UniqueConstraint("company_id", "code", name="uq_price_book_items_code"),
        sa.UniqueConstraint("company_id", "id", name="uq_price_book_items_company_id"),
    )
    op.create_index(
        "ix_price_book_items_catalog",
        "price_book_service_items",
        ["company_id", "branch_id", "status", "category_id"],
    )
    op.create_table(
        "price_book_price_versions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("service_item_id", UUID, nullable=False),
        sa.Column("branch_id", UUID),
        sa.Column("tax_classification_id", UUID, nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("rounding_mode", sa.String(40), nullable=False),
        sa.Column("activation_reason", sa.String(500)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", UUID, nullable=False),
        sa.Column("activated_by_user_id", UUID),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["activated_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "service_item_id"],
            ["price_book_service_items.company_id", "price_book_service_items.id"],
            name="fk_price_book_version_item",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_price_book_version_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "tax_classification_id"],
            [
                "price_book_tax_classifications.company_id",
                "price_book_tax_classifications.id",
            ],
            name="fk_price_book_version_tax",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('draft','active','inactive','superseded','archived')",
            name="ck_price_book_versions_status",
        ),
        sa.CheckConstraint("unit_price >= 0", name="ck_price_book_versions_price"),
        sa.CheckConstraint("version >= 1", name="ck_price_book_versions_version"),
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at > effective_at",
            name="ck_price_book_versions_window",
        ),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name="ck_price_book_versions_currency"
        ),
        sa.UniqueConstraint(
            "company_id",
            "service_item_id",
            "revision",
            name="uq_price_book_versions_revision",
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_price_book_versions_company_id"
        ),
    )
    op.create_index(
        "ix_price_book_versions_selection",
        "price_book_price_versions",
        [
            "company_id",
            "service_item_id",
            "branch_id",
            "status",
            "effective_at",
            "expires_at",
        ],
    )
    op.execute(
        """
        ALTER TABLE price_book_price_versions
        ADD CONSTRAINT ex_price_book_active_windows
        EXCLUDE USING gist (
            company_id WITH =,
            service_item_id WITH =,
            coalesce(branch_id, '00000000-0000-0000-0000-000000000000'::uuid) WITH =,
            tstzrange(effective_at, expires_at, '[)') WITH &&
        ) WHERE (status = 'active')
        DEFERRABLE INITIALLY DEFERRED
        """
    )
    op.create_foreign_key(
        "fk_price_book_item_current_version",
        "price_book_service_items",
        "price_book_price_versions",
        ["company_id", "current_version_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_table(
        "price_book_components",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("price_version_id", UUID, nullable=False),
        sa.Column("component_type", sa.String(20), nullable=False),
        sa.Column("code", sa.String(100)),
        sa.Column("label", sa.String(240), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 4)),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "price_version_id"],
            ["price_book_price_versions.company_id", "price_book_price_versions.id"],
            name="fk_price_book_component_version",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "component_type IN ('labor','material')",
            name="ck_price_book_components_type",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_price_book_components_quantity"),
        sa.CheckConstraint(
            "unit_cost IS NULL OR unit_cost >= 0", name="ck_price_book_components_cost"
        ),
        sa.UniqueConstraint(
            "company_id",
            "price_version_id",
            "position",
            name="uq_price_book_components_position",
        ),
    )
    op.create_table(
        "price_book_option_groups",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_by_user_id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "status IN ('active','archived')", name="ck_price_book_option_groups_status"
        ),
        sa.UniqueConstraint(
            "company_id", "code", name="uq_price_book_option_groups_code"
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_price_book_option_groups_company_id"
        ),
    )
    op.create_table(
        "price_book_options",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("option_group_id", UUID, nullable=False),
        sa.Column("service_item_id", UUID, nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "option_group_id"],
            ["price_book_option_groups.company_id", "price_book_option_groups.id"],
            name="fk_price_book_option_group",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "service_item_id"],
            ["price_book_service_items.company_id", "price_book_service_items.id"],
            name="fk_price_book_option_item",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "company_id",
            "option_group_id",
            "position",
            name="uq_price_book_options_position",
        ),
        sa.UniqueConstraint(
            "company_id",
            "option_group_id",
            "service_item_id",
            name="uq_price_book_options_item",
        ),
    )
    op.create_table(
        "price_book_commercial_snapshots",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("service_item_id", UUID, nullable=False),
        sa.Column("price_version_id", UUID, nullable=False),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("extended_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot_data", postgresql.JSONB(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("created_by_user_id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_price_book_snapshot_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "service_item_id"],
            ["price_book_service_items.company_id", "price_book_service_items.id"],
            name="fk_price_book_snapshot_item",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "price_version_id"],
            ["price_book_price_versions.company_id", "price_book_price_versions.id"],
            name="fk_price_book_snapshot_version",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_price_book_snapshots_quantity"),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name="ck_price_book_snapshots_currency"
        ),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_price_book_snapshots_idempotency"
        ),
        sa.Index("ix_price_book_snapshots_digest", "company_id", "digest"),
    )
    op.create_index(
        "ix_price_book_snapshots_lookup",
        "price_book_commercial_snapshots",
        ["company_id", "service_item_id", "created_at"],
    )
    op.create_table(
        "price_book_audit_entries",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", UUID, nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("actor_user_id", UUID, nullable=False),
        sa.Column("prior_state", postgresql.JSONB()),
        sa.Column("new_state", postgresql.JSONB(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("version >= 1", name="ck_price_book_audit_version"),
    )
    op.create_index(
        "ix_price_book_audit_entity",
        "price_book_audit_entries",
        ["company_id", "entity_type", "entity_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_price_book_audit_entity", table_name="price_book_audit_entries")
    op.drop_table("price_book_audit_entries")
    op.drop_index(
        "ix_price_book_snapshots_lookup", table_name="price_book_commercial_snapshots"
    )
    op.drop_table("price_book_commercial_snapshots")
    op.drop_table("price_book_options")
    op.drop_table("price_book_option_groups")
    op.drop_table("price_book_components")
    op.drop_constraint(
        "fk_price_book_item_current_version",
        "price_book_service_items",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_price_book_versions_selection", table_name="price_book_price_versions"
    )
    op.drop_table("price_book_price_versions")
    op.drop_index("ix_price_book_items_catalog", table_name="price_book_service_items")
    op.drop_table("price_book_service_items")
    op.drop_table("price_book_tax_classifications")
    op.drop_index("ix_price_book_categories_list", table_name="price_book_categories")
    op.drop_table("price_book_categories")
