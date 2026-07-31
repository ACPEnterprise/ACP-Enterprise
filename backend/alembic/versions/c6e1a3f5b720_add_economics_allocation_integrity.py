"""add economics allocation integrity

Revision ID: c6e1a3f5b720
Revises: b5d9f3a7c201
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c6e1a3f5b720"
down_revision: str | Sequence[str] | None = "b5d9f3a7c201"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "business_economics_accounting_periods",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column(
            "responsible_owner_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('open', 'closing', 'closed', 'reopened')",
            name="ck_business_economics_periods_status",
        ),
        sa.CheckConstraint(
            "period_end >= period_start", name="ck_business_economics_periods_range"
        ),
        sa.CheckConstraint(
            "version >= 1", name="ck_business_economics_periods_version"
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "period_start",
            "period_end",
            name="uq_business_economics_periods_range",
        ),
    )
    op.create_table(
        "business_economics_accounting_period_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("from_status", sa.String(12), nullable=True),
        sa.Column("to_status", sa.String(12), nullable=False),
        sa.Column(
            "responsible_owner_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "to_status IN ('open', 'closing', 'closed', 'reopened')",
            name="ck_business_economics_period_history_status",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["period_id"],
            ["business_economics_accounting_periods.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "period_id", "version", name="uq_business_economics_period_history_version"
        ),
    )
    op.add_column(
        "business_economics_allocation_runs",
        sa.Column("period_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "business_economics_allocation_runs",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "business_economics_allocation_runs",
        sa.Column(
            "execution_duration_ms", sa.BigInteger(), server_default="0", nullable=False
        ),
    )
    op.create_foreign_key(
        "fk_economics_allocation_run_period",
        "business_economics_allocation_runs",
        "business_economics_accounting_periods",
        ["period_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_business_economics_allocation_runs_version",
        "business_economics_allocation_runs",
        ["company_id", "policy_id", "version"],
    )
    op.create_table(
        "business_economics_allocation_evidence",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"], ["business_economics_allocation_runs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["business_economics_evidence_references.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("run_id", "evidence_id"),
    )
    op.create_table(
        "business_economics_reconciliation_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column("expected_count", sa.Integer(), nullable=False),
        sa.Column("actual_count", sa.Integer(), nullable=False),
        sa.Column("variance_minor", sa.BigInteger(), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('source', 'ledger', 'allocation', 'measurement', 'evidence')",
            name="ck_business_economics_reconciliation_kind",
        ),
        sa.CheckConstraint(
            "status IN ('passed', 'failed')",
            name="ck_business_economics_reconciliation_status",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["period_id"],
            ["business_economics_accounting_periods.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "input_digest",
            name="uq_business_economics_reconciliation_input",
        ),
    )
    op.create_table(
        "business_economics_profitability_projections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("scope_type", sa.String(16), nullable=False),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("measurement_count", sa.Integer(), nullable=False),
        sa.Column("values", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence_status", sa.String(12), nullable=False),
        sa.Column("confidence_percentage", sa.Integer(), nullable=False),
        sa.Column(
            "input_measurement_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "scope_type IN ('job', 'branch', 'company')",
            name="ck_business_economics_projections_scope",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "input_digest", name="uq_business_economics_projections_input"
        ),
        sa.UniqueConstraint(
            "company_id",
            "scope_type",
            "scope_id",
            "period_start",
            "period_end",
            "version",
            name="uq_business_economics_projections_version",
        ),
    )
    op.create_table(
        "business_economics_operational_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("value", sa.BigInteger(), nullable=False),
        sa.Column("labels", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "name IN ('pending_recalculations', 'allocation_execution_ms', 'materialization_duration_ms', 'reconciliation_failures', 'stale_measurements', 'incomplete_periods')",
            name="ck_business_economics_metrics_name",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_business_economics_metrics_company_observed",
        "business_economics_operational_metrics",
        ["company_id", "observed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_business_economics_metrics_company_observed",
        table_name="business_economics_operational_metrics",
    )
    op.drop_table("business_economics_operational_metrics")
    op.drop_table("business_economics_profitability_projections")
    op.drop_table("business_economics_reconciliation_results")
    op.drop_table("business_economics_allocation_evidence")
    op.drop_constraint(
        "uq_business_economics_allocation_runs_version",
        "business_economics_allocation_runs",
        type_="unique",
    )
    op.drop_constraint(
        "fk_economics_allocation_run_period",
        "business_economics_allocation_runs",
        type_="foreignkey",
    )
    op.drop_column("business_economics_allocation_runs", "execution_duration_ms")
    op.drop_column("business_economics_allocation_runs", "version")
    op.drop_column("business_economics_allocation_runs", "period_id")
    op.drop_table("business_economics_accounting_period_history")
    op.drop_table("business_economics_accounting_periods")
