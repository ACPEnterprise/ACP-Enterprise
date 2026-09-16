"""create field purchase receipt intelligence

Revision ID: a2c4e6g8i175
Revises: p6r8t0v2x4z6
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a2c4e6g8i175"
down_revision: str | Sequence[str] | None = "p6r8t0v2x4z6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "field_purchases",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("assignment_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("receipt_artifact_id", sa.UUID(), nullable=False),
        sa.Column("inventory_location_id", sa.UUID()),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("receipt_digest", sa.String(64), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("disposition_idempotency_key", sa.String(128)),
        sa.Column("disposition_request_digest", sa.String(64)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('receipt_attached','extraction_pending','review_required','ready_for_disposition','submitted')",
            name="ck_field_purchase_state",
        ),
        sa.CheckConstraint("version >= 1", name="ck_field_purchase_version"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_field_purchase_job",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"], ["dispatch_assignments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["receipt_artifact_id"], ["field_artifact_evidence.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["inventory_location_id"],
            ["inventory_stock_locations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_field_purchase_command"
        ),
        sa.UniqueConstraint(
            "company_id",
            "disposition_idempotency_key",
            name="uq_field_purchase_disposition_submission",
        ),
        sa.UniqueConstraint(
            "company_id", "receipt_artifact_id", name="uq_field_purchase_receipt"
        ),
    )
    op.create_index(
        "ix_field_purchase_review",
        "field_purchases",
        ["company_id", "branch_id", "state", "created_at"],
    )
    op.create_table(
        "field_purchase_extractions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("field_purchase_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(40), nullable=False),
        sa.Column("provider_reference", sa.String(160)),
        sa.Column("extraction_digest", sa.String(64), nullable=False),
        sa.Column("vendor_id", sa.UUID()),
        sa.Column("vendor_text", sa.String(240)),
        sa.Column("transaction_reference", sa.String(160)),
        sa.Column("purchased_at", sa.DateTime(timezone=True)),
        sa.Column("subtotal", sa.Numeric(18, 4)),
        sa.Column("tax", sa.Numeric(18, 4)),
        sa.Column("total", sa.Numeric(18, 4)),
        sa.Column("currency", sa.String(3)),
        sa.Column(
            "structured_evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("recorded_by_user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_field_purchase_extraction_version"),
        sa.CheckConstraint(
            "currency IS NULL OR currency ~ '^[A-Z]{3}$'",
            name="ck_field_purchase_currency",
        ),
        sa.ForeignKeyConstraint(
            ["field_purchase_id"], ["field_purchases.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["vendor_id"], ["purchasing_operational_vendors.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "field_purchase_id",
            "version",
            name="uq_field_purchase_extraction_version",
        ),
        sa.UniqueConstraint(
            "company_id",
            "extraction_digest",
            name="uq_field_purchase_extraction_digest",
        ),
    )
    op.create_table(
        "field_purchase_lines",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("field_purchase_id", sa.UUID(), nullable=False),
        sa.Column("extraction_id", sa.UUID(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("vendor_code", sa.String(160)),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit", sa.String(40)),
        sa.Column("unit_price", sa.Numeric(18, 4)),
        sa.Column("extended_amount", sa.Numeric(18, 4)),
        sa.Column("inventory_item_id", sa.UUID()),
        sa.Column("match_state", sa.String(24), nullable=False),
        sa.Column(
            "confidence_evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.CheckConstraint("quantity > 0", name="ck_field_purchase_line_quantity"),
        sa.CheckConstraint(
            "unit_price IS NULL OR unit_price >= 0",
            name="ck_field_purchase_line_unit_price",
        ),
        sa.CheckConstraint(
            "match_state IN ('exact','unmatched','review_required','non_inventory')",
            name="ck_field_purchase_line_match",
        ),
        sa.ForeignKeyConstraint(
            ["field_purchase_id"], ["field_purchases.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["extraction_id"], ["field_purchase_extractions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["inventory_item_id"], ["inventory_items.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "field_purchase_id",
            "line_number",
            name="uq_field_purchase_line_number",
        ),
    )
    op.create_table(
        "field_purchase_dispositions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("field_purchase_id", sa.UUID(), nullable=False),
        sa.Column("line_id", sa.UUID(), nullable=False),
        sa.Column("disposition", sa.String(32), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("inventory_location_id", sa.UUID()),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("reason", sa.String(500)),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("confirmed_by_user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "quantity > 0", name="ck_field_purchase_disposition_quantity"
        ),
        sa.CheckConstraint(
            "disposition IN ('used_on_this_job','keep_on_truck','return_or_unused','non_inventory')",
            name="ck_field_purchase_disposition_type",
        ),
        sa.CheckConstraint(
            "state IN ('pending_review','confirmed','composed')",
            name="ck_field_purchase_disposition_state",
        ),
        sa.ForeignKeyConstraint(
            ["field_purchase_id"], ["field_purchases.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["line_id"], ["field_purchase_lines.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["inventory_location_id"],
            ["inventory_stock_locations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "idempotency_key",
            name="uq_field_purchase_disposition_command",
        ),
    )
    op.create_table(
        "field_purchase_vendor_mappings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("vendor_id", sa.UUID(), nullable=False),
        sa.Column("vendor_code", sa.String(160), nullable=False),
        sa.Column("inventory_item_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("supersedes_id", sa.UUID()),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("certified_by_user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(btrim(vendor_code)) > 0", name="ck_field_purchase_mapping_code"
        ),
        sa.ForeignKeyConstraint(
            ["vendor_id"], ["purchasing_operational_vendors.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["inventory_item_id"], ["inventory_items.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["field_purchase_vendor_mappings.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["certified_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "vendor_id",
            "vendor_code",
            "version",
            name="uq_field_purchase_mapping_version",
        ),
    )
    op.create_index(
        "ix_field_purchase_mapping_active",
        "field_purchase_vendor_mappings",
        ["company_id", "vendor_id", "vendor_code", "active"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_field_purchase_mapping_active", table_name="field_purchase_vendor_mappings"
    )
    op.drop_table("field_purchase_vendor_mappings")
    op.drop_table("field_purchase_dispositions")
    op.drop_table("field_purchase_lines")
    op.drop_table("field_purchase_extractions")
    op.drop_index("ix_field_purchase_review", table_name="field_purchases")
    op.drop_table("field_purchases")
