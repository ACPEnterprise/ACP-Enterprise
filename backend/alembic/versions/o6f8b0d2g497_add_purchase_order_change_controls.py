"""add purchase order change controls

Revision ID: o6f8b0d2g497
Revises: n5e7a9c1f386
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "o6f8b0d2g497"
down_revision = "n5e7a9c1f386"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "purchasing_purchase_orders",
        sa.Column(
            "effective_revision", sa.Integer(), nullable=False, server_default="1"
        ),
    )
    op.add_column(
        "purchasing_purchase_order_lines",
        sa.Column(
            "is_cancelled", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.create_table(
        "purchasing_po_change_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purchase_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("change_identity", sa.String(128), nullable=False),
        sa.Column("base_revision", sa.Integer(), nullable=False),
        sa.Column("proposed_changes", postgresql.JSONB(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "requested_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "decided_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("effective_revision", sa.Integer()),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column(
            "downstream_reconciliation_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "purchase_order_id"],
            ["purchasing_purchase_orders.company_id", "purchasing_purchase_orders.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("company_id", "change_identity"),
        sa.UniqueConstraint("company_id", "id"),
        sa.CheckConstraint("status IN ('requested','approved','rejected')"),
    )
    op.create_table(
        "purchasing_po_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purchase_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("predecessor_revision", sa.Integer()),
        sa.Column(
            "change_order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("purchasing_po_change_orders.id", ondelete="RESTRICT"),
        ),
        sa.Column("effective_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column(
            "effective_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "purchase_order_id"],
            ["purchasing_purchase_orders.company_id", "purchasing_purchase_orders.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("company_id", "purchase_order_id", "revision_number"),
    )


def downgrade() -> None:
    op.drop_table("purchasing_po_revisions")
    op.drop_table("purchasing_po_change_orders")
    op.drop_column("purchasing_purchase_order_lines", "is_cancelled")
    op.drop_column("purchasing_purchase_orders", "effective_revision")
