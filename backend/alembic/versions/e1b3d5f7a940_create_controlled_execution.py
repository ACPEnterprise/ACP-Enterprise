"""create controlled engineering execution

Revision ID: e1b3d5f7a940
Revises: d3f5a7c9e162
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e1b3d5f7a940"
down_revision: str | None = "d3f5a7c9e162"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "engineering_controlled_execution_offers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.String(length=100), nullable=False),
        sa.Column("command_type", sa.String(length=50), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("capability_required", sa.String(length=100), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_seconds", sa.Integer(), nullable=False),
        sa.Column("lease_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "command_type = 'inspect_workspace'",
            name="ck_controlled_offers_command_type",
        ),
        sa.CheckConstraint(
            "capability_required = 'engineering.execute'",
            name="ck_controlled_offers_capability",
        ),
        sa.CheckConstraint(
            "state IN ('available','acquired','completed','failed','cancelled','expired')",
            name="ck_controlled_offers_state",
        ),
        sa.CheckConstraint(
            "lease_seconds BETWEEN 30 AND 900", name="ck_controlled_offers_lease"
        ),
        sa.CheckConstraint("version >= 1", name="ck_controlled_offers_version"),
        sa.CheckConstraint(
            "expires_at > created_at", name="ck_controlled_offers_expiration"
        ),
        sa.CheckConstraint(
            "(state = 'available' AND lease_id IS NULL AND worker_id IS NULL "
            "AND session_id IS NULL AND acquired_at IS NULL) OR "
            "(state IN ('acquired','completed','failed') AND lease_id IS NOT NULL "
            "AND worker_id IS NOT NULL AND session_id IS NOT NULL "
            "AND acquired_at IS NOT NULL) OR state IN ('cancelled','expired')",
            name="ck_controlled_offers_acquisition_binding",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["command_id"], ["engineering_commands.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "execution_id"],
            ["engineering_executions.company_id", "engineering_executions.id"],
            name="fk_controlled_offers_execution",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "execution_id", name="uq_controlled_offers_execution"
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_controlled_offers_company_id"),
    )
    op.create_index(
        "ix_controlled_offers_company_state_expiry",
        "engineering_controlled_execution_offers",
        ["company_id", "state", "expires_at", "id"],
    )
    op.create_table(
        "engineering_controlled_execution_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("offer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lease_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_classification", sa.String(length=100), nullable=True),
        sa.Column("repository_mutated", sa.Boolean(), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('succeeded','failed','timed_out','cancelled')",
            name="ck_controlled_results_outcome",
        ),
        sa.CheckConstraint(
            "repository_mutated = false",
            name="ck_controlled_results_repository_immutable",
        ),
        sa.CheckConstraint(
            "completed_at >= started_at", name="ck_controlled_results_timestamps"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "offer_id"],
            [
                "engineering_controlled_execution_offers.company_id",
                "engineering_controlled_execution_offers.id",
            ],
            name="fk_controlled_results_offer",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "offer_id", name="uq_controlled_results_offer"
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_controlled_results_company_id"
        ),
    )
    op.create_index(
        "ix_controlled_results_company_execution",
        "engineering_controlled_execution_results",
        ["company_id", "execution_id", "created_at", "id"],
    )
    op.add_column(
        "engineering_execution_reviews",
        sa.Column("controlled_result_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.alter_column("engineering_execution_reviews", "composition_id", nullable=True)
    op.alter_column("engineering_execution_reviews", "attempt_id", nullable=True)
    op.alter_column("engineering_execution_reviews", "result_id", nullable=True)
    op.create_foreign_key(
        "fk_engineering_execution_reviews_controlled_result",
        "engineering_execution_reviews",
        "engineering_controlled_execution_results",
        ["controlled_result_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_engineering_execution_reviews_controlled_result",
        "engineering_execution_reviews",
        ["company_id", "controlled_result_id"],
    )
    op.create_check_constraint(
        "ck_engineering_execution_reviews_evidence_source",
        "engineering_execution_reviews",
        "(controlled_result_id IS NULL AND composition_id IS NOT NULL "
        "AND attempt_id IS NOT NULL AND result_id IS NOT NULL) OR "
        "(controlled_result_id IS NOT NULL AND composition_id IS NULL "
        "AND attempt_id IS NULL AND result_id IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_engineering_execution_reviews_evidence_source",
        "engineering_execution_reviews",
        type_="check",
    )
    op.drop_constraint(
        "uq_engineering_execution_reviews_controlled_result",
        "engineering_execution_reviews",
        type_="unique",
    )
    op.drop_constraint(
        "fk_engineering_execution_reviews_controlled_result",
        "engineering_execution_reviews",
        type_="foreignkey",
    )
    op.drop_column("engineering_execution_reviews", "controlled_result_id")
    op.alter_column("engineering_execution_reviews", "result_id", nullable=False)
    op.alter_column("engineering_execution_reviews", "attempt_id", nullable=False)
    op.alter_column("engineering_execution_reviews", "composition_id", nullable=False)
    op.drop_index(
        "ix_controlled_results_company_execution",
        table_name="engineering_controlled_execution_results",
    )
    op.drop_table("engineering_controlled_execution_results")
    op.drop_index(
        "ix_controlled_offers_company_state_expiry",
        table_name="engineering_controlled_execution_offers",
    )
    op.drop_table("engineering_controlled_execution_offers")
