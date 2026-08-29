"""Add HCP generation-2 repair lineage.

Revision ID: c6e8a0b2d435
Revises: b5d7f9a1c324
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c6e8a0b2d435"
down_revision: str | Sequence[str] | None = "b5d7f9a1c324"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "hcp_appointment_sequence_plans",
        sa.Column(
            "retained_identity_digests",
            postgresql.JSONB(),
            server_default="[]",
            nullable=False,
        ),
    )
    op.add_column(
        "hcp_appointment_sequence_plans",
        sa.Column(
            "remaining_identity_digests",
            postgresql.JSONB(),
            server_default="[]",
            nullable=False,
        ),
    )
    op.add_column(
        "hcp_migration_child_repairs",
        sa.Column("parent_repair_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "hcp_migration_child_repairs",
        sa.Column("failed_child_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "hcp_migration_child_repairs",
        sa.Column("sequence_plan_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "hcp_migration_child_repairs",
        sa.Column(
            "repair_generation", sa.Integer(), server_default="1", nullable=False
        ),
    )
    op.create_check_constraint(
        "ck_hcp_child_repair_generation",
        "hcp_migration_child_repairs",
        "repair_generation >= 1",
    )
    op.create_foreign_key(
        "fk_hcp_child_repair_parent",
        "hcp_migration_child_repairs",
        "hcp_migration_child_repairs",
        ["parent_repair_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_hcp_child_repair_failed_child",
        "hcp_migration_child_repairs",
        "operational_migration_runs",
        ["failed_child_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_hcp_child_repair_sequence_plan",
        "hcp_migration_child_repairs",
        "hcp_appointment_sequence_plans",
        ["sequence_plan_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_hcp_child_repair_generation",
        "hcp_migration_child_repairs",
        ["master_run_id", "domain", "repair_generation"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_hcp_child_repair_generation",
        "hcp_migration_child_repairs",
        type_="unique",
    )
    op.drop_constraint(
        "fk_hcp_child_repair_sequence_plan",
        "hcp_migration_child_repairs",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_hcp_child_repair_failed_child",
        "hcp_migration_child_repairs",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_hcp_child_repair_parent",
        "hcp_migration_child_repairs",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_hcp_child_repair_generation",
        "hcp_migration_child_repairs",
        type_="check",
    )
    op.drop_column("hcp_migration_child_repairs", "repair_generation")
    op.drop_column("hcp_migration_child_repairs", "sequence_plan_id")
    op.drop_column("hcp_migration_child_repairs", "failed_child_run_id")
    op.drop_column("hcp_migration_child_repairs", "parent_repair_id")
    op.drop_column("hcp_appointment_sequence_plans", "remaining_identity_digests")
    op.drop_column("hcp_appointment_sequence_plans", "retained_identity_digests")
