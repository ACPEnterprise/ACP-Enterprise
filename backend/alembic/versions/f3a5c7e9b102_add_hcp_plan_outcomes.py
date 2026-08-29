"""Add durable master-bound HCP execution-plan outcomes.

Revision ID: f3a5c7e9b102
Revises: e2f4a6b8c091
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f3a5c7e9b102"
down_revision: str | Sequence[str] | None = "e2f4a6b8c091"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hcp_migration_plan_outcomes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("master_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_kind", sa.String(40), nullable=False),
        sa.Column("native_identity_sha256", sa.String(64), nullable=False),
        sa.Column("outcome", sa.String(40), nullable=False),
        sa.Column("reason_code", sa.String(100), nullable=False),
        sa.Column("package_digest", sa.String(64), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("transformation_version", sa.String(100), nullable=False),
        sa.Column("outcome_digest", sa.String(64), nullable=False),
        sa.Column("operational_effects_enabled", sa.Boolean(), nullable=False),
        sa.Column("financial_truth_accepted", sa.Boolean(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('EXPLICIT_EXCEPTION','REJECTED','INTENTIONALLY_NON_APPLICABLE')",
            name="ck_hcp_plan_outcome_class",
        ),
        sa.CheckConstraint(
            "operational_effects_enabled = false AND financial_truth_accepted = false",
            name="ck_hcp_plan_outcome_no_effects",
        ),
        sa.ForeignKeyConstraint(
            ["master_run_id", "company_id", "branch_id"],
            [
                "hcp_migration_master_runs.id",
                "hcp_migration_master_runs.company_id",
                "hcp_migration_master_runs.branch_id",
            ],
            name="fk_hcp_plan_outcome_master_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "master_run_id",
            "entity_kind",
            "native_identity_sha256",
            name="uq_hcp_plan_outcome_native",
        ),
        sa.UniqueConstraint(
            "company_id", "outcome_digest", name="uq_hcp_plan_outcome_replay"
        ),
    )


def downgrade() -> None:
    op.drop_table("hcp_migration_plan_outcomes")
