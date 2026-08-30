"""create supply chain demand and policy authority

Revision ID: 18h3j78973i7
Revises: 17g2i67862h6
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "18h3j78973i7"
down_revision: str | Sequence[str] | None = "17g2i67862h6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "purchasing_requisitions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("request_number", sa.String(80), nullable=False),
        sa.Column("inventory_item_id", sa.UUID(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit", sa.String(40), nullable=False),
        sa.Column("need_by", sa.Date(), nullable=True),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("source_reference", sa.String(240), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=True),
        sa.Column("suggested_vendor_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("requester_user_id", sa.UUID(), nullable=False),
        sa.Column("decided_by_user_id", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("purchase_order_id", sa.UUID(), nullable=True),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_purchasing_requisition_quantity"),
        sa.CheckConstraint(
            "status IN ('draft','submitted','approved','rejected','cancelled','converted')",
            name="ck_purchasing_requisition_status",
        ),
        sa.CheckConstraint(
            "source_type IN ('manual','replenishment','job_material','stock_location','emergency_exception')",
            name="ck_purchasing_requisition_source",
        ),
        sa.CheckConstraint("version >= 1", name="ck_purchasing_requisition_version"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_purchasing_requisition_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "inventory_item_id"],
            ["inventory_items.company_id", "inventory_items.id"],
            name="fk_purchasing_requisition_item",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "suggested_vendor_id"],
            [
                "purchasing_operational_vendors.company_id",
                "purchasing_operational_vendors.id",
            ],
            name="fk_purchasing_requisition_vendor",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "purchase_order_id"],
            ["purchasing_purchase_orders.company_id", "purchasing_purchase_orders.id"],
            name="fk_purchasing_requisition_po",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requester_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "request_number", name="uq_purchasing_requisition_number"
        ),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_purchasing_requisition_key"
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_purchasing_requisition_company"
        ),
    )
    op.create_index(
        "ix_purchasing_requisition_queue",
        "purchasing_requisitions",
        ["company_id", "branch_id", "status", "need_by"],
    )
    op.create_table(
        "supply_chain_policies",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("policy_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "configuration", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("readiness_reason", sa.Text(), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_by_user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "policy_type IN ('matching_tolerance','receiving','reorder','valuation','receipt_accrual','approval')",
            name="ck_supply_chain_policy_type",
        ),
        sa.CheckConstraint(
            "status IN ('unconfigured','draft','active','inactive')",
            name="ck_supply_chain_policy_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_supply_chain_policy_version"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_supply_chain_policy_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "branch_id",
            "policy_type",
            name="uq_supply_chain_policy_scope",
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_supply_chain_policy_company"),
    )


def downgrade() -> None:
    op.drop_table("supply_chain_policies")
    op.drop_index(
        "ix_purchasing_requisition_queue", table_name="purchasing_requisitions"
    )
    op.drop_table("purchasing_requisitions")
