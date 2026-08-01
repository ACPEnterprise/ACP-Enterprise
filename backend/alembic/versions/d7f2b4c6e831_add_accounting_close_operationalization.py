"""add accounting close operationalization

Revision ID: d7f2b4c6e831
Revises: c6e1a3f5b720
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d7f2b4c6e831"
down_revision: str | Sequence[str] | None = "c6e1a3f5b720"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    op.drop_constraint(
        "ck_business_economics_metrics_name",
        "business_economics_operational_metrics",
        type_="check",
    )
    op.create_check_constraint(
        "ck_business_economics_metrics_name",
        "business_economics_operational_metrics",
        "name IN ('pending_recalculations', 'allocation_execution_ms', 'materialization_duration_ms', 'reconciliation_failures', 'stale_measurements', 'incomplete_periods', 'scheduled_processing_failures', 'scheduled_processing_duration_ms')",
    )
    op.create_table(
        "business_economics_source_bindings",
        sa.Column("id", uuid, nullable=False),
        sa.Column("company_id", uuid, nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("owner_domain", sa.String(80), nullable=False),
        sa.Column("source_table", sa.String(100)),
        sa.Column("adapter_key", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("evidence_requirements", jsonb, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('bound', 'read_only', 'contract_ready', 'unavailable')",
            name="ck_business_economics_source_bindings_status",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "source_type",
            "version",
            name="uq_business_economics_source_bindings_version",
        ),
    )
    op.create_table(
        "business_economics_processing_work_items",
        sa.Column("id", uuid, nullable=False),
        sa.Column("company_id", uuid, nullable=False),
        sa.Column("period_id", uuid),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("scope_type", sa.String(32), nullable=False),
        sa.Column("scope_id", uuid, nullable=False),
        sa.Column("payload", jsonb, nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("failure_evidence_digest", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('recalculation', 'allocation', 'materialization', 'publication', 'reconciliation', 'monitoring')",
            name="ck_business_economics_work_items_kind",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'retry_scheduled', 'completed', 'failed')",
            name="ck_business_economics_work_items_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND max_attempts >= 1",
            name="ck_business_economics_work_items_attempts",
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
            "idempotency_key",
            name="uq_business_economics_work_items_idempotency",
        ),
    )
    op.create_index(
        "ix_business_economics_work_items_claim",
        "business_economics_processing_work_items",
        ["status", "available_at", "created_at"],
    )
    op.create_table(
        "business_economics_accounting_mappings",
        sa.Column("id", uuid, nullable=False),
        sa.Column("company_id", uuid, nullable=False),
        sa.Column("mapping_key", sa.String(100), nullable=False),
        sa.Column("classification", sa.String(20), nullable=False),
        sa.Column("account_code", sa.String(100), nullable=False),
        sa.Column("branch_dimension_key", sa.String(100)),
        sa.Column("dimensions", jsonb, nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "classification IN ('revenue', 'labor', 'materials', 'equipment', 'truck', 'overhead', 'payment', 'allocation')",
            name="ck_business_economics_accounting_mapping_class",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "mapping_key",
            "version",
            name="uq_business_economics_accounting_mapping_version",
        ),
    )
    op.create_table(
        "business_economics_accounting_exports",
        sa.Column("id", uuid, nullable=False),
        sa.Column("company_id", uuid, nullable=False),
        sa.Column("period_id", uuid, nullable=False),
        sa.Column("export_key", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("debit_minor", sa.BigInteger(), nullable=False),
        sa.Column("credit_minor", sa.BigInteger(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("source_projection_ids", jsonb, nullable=False),
        sa.Column("corrects_export_id", uuid),
        sa.Column("acknowledgement_reference", sa.String(200)),
        sa.Column("rejection_reason", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('prepared', 'exported', 'acknowledged', 'rejected', 'corrected')",
            name="ck_business_economics_accounting_exports_status",
        ),
        sa.CheckConstraint(
            "debit_minor = credit_minor",
            name="ck_business_economics_accounting_exports_balance",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["period_id"],
            ["business_economics_accounting_periods.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["corrects_export_id"],
            ["business_economics_accounting_exports.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "export_key",
            "version",
            name="uq_business_economics_accounting_exports_version",
        ),
        sa.UniqueConstraint(
            "company_id",
            "checksum",
            name="uq_business_economics_accounting_exports_checksum",
        ),
    )
    op.create_table(
        "business_economics_accounting_journal_lines",
        sa.Column("id", uuid, nullable=False),
        sa.Column("company_id", uuid, nullable=False),
        sa.Column("export_id", uuid, nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("account_code", sa.String(100), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("branch_id", uuid),
        sa.Column("source_reference", sa.String(200), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("dimensions", jsonb, nullable=False),
        sa.CheckConstraint(
            "side IN ('debit', 'credit')",
            name="ck_business_economics_journal_lines_side",
        ),
        sa.CheckConstraint(
            "amount_minor > 0", name="ck_business_economics_journal_lines_amount"
        ),
        sa.ForeignKeyConstraint(
            ["export_id"],
            ["business_economics_accounting_exports.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "export_id",
            "line_number",
            name="uq_business_economics_journal_lines_number",
        ),
    )
    op.create_table(
        "business_economics_close_readiness",
        sa.Column("id", uuid, nullable=False),
        sa.Column("company_id", uuid, nullable=False),
        sa.Column("period_id", uuid, nullable=False),
        sa.Column("responsible_owner_id", uuid, nullable=False),
        sa.Column("ready", sa.Boolean(), nullable=False),
        sa.Column("checks", jsonb, nullable=False),
        sa.Column("blockers", jsonb, nullable=False),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["period_id"],
            ["business_economics_accounting_periods.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "period_id",
            "version",
            name="uq_business_economics_close_readiness_version",
        ),
        sa.UniqueConstraint(
            "company_id",
            "input_digest",
            name="uq_business_economics_close_readiness_input",
        ),
    )
    op.create_table(
        "business_economics_gl_reconciliations",
        sa.Column("id", uuid, nullable=False),
        sa.Column("company_id", uuid, nullable=False),
        sa.Column("period_id", uuid, nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("source_represented_minor", sa.BigInteger()),
        sa.Column("exported_minor", sa.BigInteger()),
        sa.Column("journal_balance_minor", sa.BigInteger(), nullable=False),
        sa.Column("rejected_line_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_export_count", sa.Integer(), nullable=False),
        sa.Column("correction_count", sa.Integer(), nullable=False),
        sa.Column("period_variance_minor", sa.BigInteger()),
        sa.Column("ownership_mismatch_count", sa.Integer(), nullable=False),
        sa.Column("unexplained_residual_minor", sa.BigInteger()),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('passed', 'failed', 'unknown')",
            name="ck_business_economics_gl_reconciliation_status",
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
            "period_id",
            "version",
            name="uq_business_economics_gl_reconciliation_version",
        ),
        sa.UniqueConstraint(
            "company_id",
            "input_digest",
            name="uq_business_economics_gl_reconciliation_input",
        ),
    )
    op.create_table(
        "business_economics_period_audit_packages",
        sa.Column("id", uuid, nullable=False),
        sa.Column("company_id", uuid, nullable=False),
        sa.Column("period_id", uuid, nullable=False),
        sa.Column("manifest", jsonb, nullable=False),
        sa.Column("package_digest", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["period_id"],
            ["business_economics_accounting_periods.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "period_id",
            "version",
            name="uq_business_economics_audit_packages_version",
        ),
        sa.UniqueConstraint(
            "company_id",
            "package_digest",
            name="uq_business_economics_audit_packages_digest",
        ),
    )
    op.create_table(
        "business_economics_integrity_publications",
        sa.Column("id", uuid, nullable=False),
        sa.Column("company_id", uuid, nullable=False),
        sa.Column("projection_id", uuid, nullable=False),
        sa.Column("period_id", uuid, nullable=False),
        sa.Column("confidence_status", sa.String(12), nullable=False),
        sa.Column("confidence_percentage", sa.Integer(), nullable=False),
        sa.Column("completeness_percentage", sa.Integer(), nullable=False),
        sa.Column("freshness_status", sa.String(12), nullable=False),
        sa.Column("evidence_lineage", jsonb, nullable=False),
        sa.Column("integrity_status", sa.String(16), nullable=False),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "integrity_status IN ('reconciled', 'incomplete', 'stale', 'unknown')",
            name="ck_business_economics_integrity_publication_status",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["projection_id"],
            ["business_economics_profitability_projections.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["period_id"],
            ["business_economics_accounting_periods.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "projection_id",
            "version",
            name="uq_business_economics_integrity_publication_version",
        ),
        sa.UniqueConstraint(
            "company_id",
            "input_digest",
            name="uq_business_economics_integrity_publication_input",
        ),
    )


def downgrade() -> None:
    op.drop_table("business_economics_integrity_publications")
    op.drop_table("business_economics_period_audit_packages")
    op.drop_table("business_economics_gl_reconciliations")
    op.drop_table("business_economics_close_readiness")
    op.drop_table("business_economics_accounting_journal_lines")
    op.drop_table("business_economics_accounting_exports")
    op.drop_table("business_economics_accounting_mappings")
    op.drop_index(
        "ix_business_economics_work_items_claim",
        table_name="business_economics_processing_work_items",
    )
    op.drop_table("business_economics_processing_work_items")
    op.drop_table("business_economics_source_bindings")
    op.drop_constraint(
        "ck_business_economics_metrics_name",
        "business_economics_operational_metrics",
        type_="check",
    )
    op.execute(
        sa.text(
            "DELETE FROM business_economics_operational_metrics "
            "WHERE name IN ('scheduled_processing_failures', "
            "'scheduled_processing_duration_ms')"
        )
    )
    op.create_check_constraint(
        "ck_business_economics_metrics_name",
        "business_economics_operational_metrics",
        "name IN ('pending_recalculations', 'allocation_execution_ms', 'materialization_duration_ms', 'reconciliation_failures', 'stale_measurements', 'incomplete_periods')",
    )
