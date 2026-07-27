"""Create controlled Customer migration persistence.

Revision ID: e8b4c6d2a917
Revises: d3f5a7c9e162
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e8b4c6d2a917"
down_revision: str | Sequence[str] | None = "d3f5a7c9e162"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customer_billing_addresses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("address_line_1", sa.String(length=200), nullable=False),
        sa.Column("address_line_2", sa.String(length=200), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("state", sa.String(length=100), nullable=False),
        sa.Column("postal_code", sa.String(length=20), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("normalized_address", sa.String(length=500), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name="fk_customer_billing_addresses_customer_id_customers",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_customer_billing_addresses_customer_id_active",
        "customer_billing_addresses",
        ["customer_id", "active"],
    )
    op.create_index(
        "uq_customer_billing_addresses_active_primary",
        "customer_billing_addresses",
        ["customer_id"],
        unique=True,
        postgresql_where=sa.text("is_primary AND active AND archived_at IS NULL"),
    )
    op.create_table(
        "customer_migration_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "initiated_by_user_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("source_system", sa.String(length=50), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("accepted_count", sa.Integer(), nullable=False),
        sa.Column("rejected_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), nullable=False),
        sa.Column("unresolved_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "mode IN ('dry_run', 'import')",
            name="ck_customer_migration_runs_mode",
        ),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_customer_migration_runs_status",
        ),
        sa.CheckConstraint(
            "source_count >= 0 AND accepted_count >= 0 AND rejected_count >= 0 "
            "AND duplicate_count >= 0 AND unresolved_count >= 0",
            name="ck_customer_migration_runs_counts_nonnegative",
        ),
        sa.CheckConstraint(
            "source_count = accepted_count + rejected_count + duplicate_count "
            "+ unresolved_count",
            name="ck_customer_migration_runs_counts_reconcile",
        ),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["initiated_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "customer_source_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(length=50), nullable=False),
        sa.Column("source_customer_id", sa.String(length=191), nullable=False),
        sa.Column("first_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["first_run_id"], ["customer_migration_runs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "source_system",
            "source_customer_id",
            name="uq_customer_source_identity",
        ),
        sa.UniqueConstraint(
            "company_id",
            "source_system",
            "customer_id",
            name="uq_customer_source_target",
        ),
    )
    op.create_table(
        "customer_migration_exceptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("source_id_sha256", sa.String(length=64), nullable=True),
        sa.Column("disposition", sa.String(length=20), nullable=False),
        sa.Column("reason_code", sa.String(length=80), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "disposition IN ('rejected', 'duplicate', 'unresolved')",
            name="ck_customer_migration_exceptions_disposition",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["customer_migration_runs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("customer_migration_exceptions")
    op.drop_table("customer_source_identities")
    op.drop_table("customer_migration_runs")
    op.drop_index(
        "uq_customer_billing_addresses_active_primary",
        table_name="customer_billing_addresses",
    )
    op.drop_index(
        "ix_customer_billing_addresses_customer_id_active",
        table_name="customer_billing_addresses",
    )
    op.drop_table("customer_billing_addresses")
