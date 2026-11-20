"""Create provider-neutral customer file import staging.

Revision ID: r4s6u8w0y2a4
Revises: zq9s1u3w5y7c
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "r4s6u8w0y2a4"
down_revision: str | Sequence[str] | None = "zq9s1u3w5y7c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customer_import_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_key", sa.String(length=64), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_provider", sa.String(length=80), nullable=False),
        sa.Column("source_namespace", sa.String(length=80), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("mapping_sha256", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=100), nullable=False),
        sa.Column("file_format", sa.String(length=10), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("ready_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), nullable=False),
        sa.Column("held_count", sa.Integer(), nullable=False),
        sa.Column("rejected_count", sa.Integer(), nullable=False),
        sa.Column("cursor_row", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("migration_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("file_format IN ('csv', 'xlsx')", name="ck_customer_import_batch_format"),
        sa.CheckConstraint(
            "status IN ('staged', 'paused', 'completed', 'failed')",
            name="ck_customer_import_batch_status",
        ),
        sa.CheckConstraint(
            "row_count >= 0 AND ready_count >= 0 AND duplicate_count >= 0 "
            "AND held_count >= 0 AND rejected_count >= 0 AND cursor_row >= 1",
            name="ck_customer_import_batch_counts",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_customer_import_batch_branch_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["migration_run_id"], ["customer_migration_runs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_key", name="uq_customer_import_batch_key"),
        sa.UniqueConstraint("id", "company_id", "branch_id", name="uq_customer_import_batch_scope"),
        sa.UniqueConstraint(
            "company_id",
            "branch_id",
            "source_provider",
            "source_namespace",
            "source_sha256",
            "mapping_sha256",
            name="uq_customer_import_batch_source",
        ),
    )
    op.create_index(
        "ix_customer_import_batches_tenant_created",
        "customer_import_batches",
        ["company_id", "branch_id", "created_at"],
    )

    op.create_table(
        "customer_import_rows",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("source_record_id", sa.String(length=191), nullable=False),
        sa.Column("source_identity_key", sa.String(length=400), nullable=False),
        sa.Column("source_row_sha256", sa.String(length=64), nullable=False),
        sa.Column("disposition", sa.String(length=20), nullable=False),
        sa.Column("reason_code", sa.String(length=80), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("validation_errors", postgresql.JSONB(), nullable=False),
        sa.Column("processed", sa.Boolean(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "disposition IN ('ready', 'duplicate', 'held', 'rejected')",
            name="ck_customer_import_row_disposition",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id", "company_id", "branch_id"],
            ["customer_import_batches.id", "customer_import_batches.company_id", "customer_import_batches.branch_id"],
            name="fk_customer_import_row_batch_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id", "row_number", name="uq_customer_import_row_number"),
        sa.UniqueConstraint("batch_id", "source_identity_key", name="uq_customer_import_row_identity"),
    )
    op.create_index(
        "ix_customer_import_rows_batch_disposition",
        "customer_import_rows",
        ["batch_id", "disposition"],
    )

    op.create_table(
        "customer_import_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_key", sa.String(length=191), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["batch_id", "company_id", "branch_id"],
            ["customer_import_batches.id", "customer_import_batches.company_id", "customer_import_batches.branch_id"],
            name="fk_customer_import_audit_batch_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id", "event_key", name="uq_customer_import_audit_event"),
    )
    op.create_index(
        "ix_customer_import_audit_tenant_created",
        "customer_import_audit_events",
        ["company_id", "branch_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_customer_import_audit_tenant_created", table_name="customer_import_audit_events")
    op.drop_table("customer_import_audit_events")
    op.drop_index("ix_customer_import_rows_batch_disposition", table_name="customer_import_rows")
    op.drop_table("customer_import_rows")
    op.drop_index("ix_customer_import_batches_tenant_created", table_name="customer_import_batches")
    op.drop_table("customer_import_batches")
