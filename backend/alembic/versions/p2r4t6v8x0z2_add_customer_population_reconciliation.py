"""add durable Customer population reconciliation authority

Revision ID: p2r4t6v8x0z2
Revises: o1q9s27h4u0v
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "p2r4t6v8x0z2"
down_revision: str | Sequence[str] | None = "o1q9s27h4u0v"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customer_population_reconciliation_dispositions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_row_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "customer_source_identity_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_system", sa.String(length=50), nullable=False),
        sa.Column("source_customer_id", sa.String(length=191), nullable=False),
        sa.Column("source_identity_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_row_sha256", sa.String(length=64), nullable=False),
        sa.Column("disposition", sa.String(length=20), nullable=False),
        sa.Column("reason_code", sa.String(length=80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("evidence_digest", sa.String(length=64), nullable=False),
        sa.Column("decided_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "disposition IN ('BOUND','HELD','AMBIGUOUS','UNEXPLAINED')",
            name="ck_customer_population_disposition_state",
        ),
        sa.CheckConstraint(
            "version >= 1", name="ck_customer_population_disposition_version"
        ),
        sa.CheckConstraint(
            "(disposition = 'BOUND') = "
            "(customer_source_identity_id IS NOT NULL AND customer_id IS NOT NULL)",
            name="ck_customer_population_disposition_bound_target",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_customer_population_disposition_branch_company",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_artifact_id"],
            ["customer_migration_source_artifacts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_row_id"],
            ["customer_migration_source_rows.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "customer_source_identity_id",
                "company_id",
                "branch_id",
                "customer_id",
            ],
            [
                "customer_source_identities.id",
                "customer_source_identities.company_id",
                "customer_source_identities.branch_id",
                "customer_source_identities.customer_id",
            ],
            name="fk_customer_population_disposition_target_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "source_system",
            "source_customer_id",
            "version",
            name="uq_customer_population_disposition_version",
        ),
        sa.UniqueConstraint(
            "id", "company_id", name="uq_customer_population_disposition_scope"
        ),
        sa.UniqueConstraint(
            "company_id",
            "source_system",
            "source_customer_id",
            "evidence_digest",
            name="uq_customer_population_disposition_evidence",
        ),
    )
    op.create_index(
        "ix_customer_population_disposition_current",
        "customer_population_reconciliation_dispositions",
        ["company_id", "branch_id", "source_system", "source_customer_id", "version"],
    )
    op.create_index(
        "ix_customer_population_disposition_queue",
        "customer_population_reconciliation_dispositions",
        ["company_id", "branch_id", "source_system", "disposition"],
    )
    op.create_table(
        "customer_population_reconciliation_commands",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(length=50), nullable=False),
        sa.Column("source_customer_id", sa.String(length=191), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "result_disposition_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("result_counts", postgresql.JSONB(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column(
            "initiated_by_user_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending','completed','failed')",
            name="ck_customer_population_command_status",
        ),
        sa.CheckConstraint(
            "(status = 'completed') = "
            "(result_disposition_id IS NOT NULL AND customer_id IS NOT NULL "
            "AND result_counts IS NOT NULL)",
            name="ck_customer_population_command_completed_result",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_customer_population_command_branch_company",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["result_disposition_id", "company_id"],
            [
                "customer_population_reconciliation_dispositions.id",
                "customer_population_reconciliation_dispositions.company_id",
            ],
            name="fk_customer_population_command_result_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["initiated_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "idempotency_key",
            name="uq_customer_population_command_idempotency",
        ),
    )
    op.create_index(
        "ix_customer_population_command_provider",
        "customer_population_reconciliation_commands",
        ["company_id", "source_system", "source_customer_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_customer_population_command_provider",
        table_name="customer_population_reconciliation_commands",
    )
    op.drop_table("customer_population_reconciliation_commands")
    op.drop_index(
        "ix_customer_population_disposition_queue",
        table_name="customer_population_reconciliation_dispositions",
    )
    op.drop_index(
        "ix_customer_population_disposition_current",
        table_name="customer_population_reconciliation_dispositions",
    )
    op.drop_table("customer_population_reconciliation_dispositions")
