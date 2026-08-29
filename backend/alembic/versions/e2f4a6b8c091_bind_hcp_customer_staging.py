"""Bind HCP Customer staging and native Location lineage to the master.

Revision ID: e2f4a6b8c091
Revises: d7f1b3c5e068
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e2f4a6b8c091"
down_revision: str | Sequence[str] | None = "d7f1b3c5e068"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for name, column in (
        ("master_run_id", sa.Column("master_run_id", postgresql.UUID(as_uuid=True))),
        ("actor_user_id", sa.Column("actor_user_id", postgresql.UUID(as_uuid=True))),
        ("package_digest", sa.Column("package_digest", sa.String(64))),
        (
            "hybrid_admission_digest",
            sa.Column("hybrid_admission_digest", sa.String(64)),
        ),
        ("staging_digest", sa.Column("staging_digest", sa.String(64))),
    ):
        del name
        op.add_column("customer_migration_source_artifacts", column)
    op.create_foreign_key(
        "fk_customer_source_artifact_master_scope",
        "customer_migration_source_artifacts",
        "hcp_migration_master_runs",
        ["master_run_id", "company_id", "branch_id", "actor_user_id"],
        ["id", "company_id", "branch_id", "actor_user_id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_customer_source4_artifact_master_required",
        "customer_migration_source_artifacts",
        "source_system <> 'housecall_pro_source4' OR "
        "(master_run_id IS NOT NULL AND package_digest IS NOT NULL AND "
        "hybrid_admission_digest IS NOT NULL AND actor_user_id IS NOT NULL AND "
        "staging_digest IS NOT NULL)",
    )

    op.add_column(
        "service_location_source_identities",
        sa.Column("branch_id", postgresql.UUID(as_uuid=True)),
    )
    op.add_column(
        "service_location_source_identities",
        sa.Column("master_run_id", postgresql.UUID(as_uuid=True)),
    )
    op.add_column(
        "service_location_source_identities", sa.Column("source_digest", sa.String(64))
    )
    op.add_column(
        "service_location_source_identities", sa.Column("package_digest", sa.String(64))
    )
    op.add_column(
        "service_location_source_identities",
        sa.Column("transformation_version", sa.String(100)),
    )
    op.add_column(
        "service_location_source_identities",
        sa.Column("transformation_digest", sa.String(64)),
    )
    op.add_column(
        "service_location_source_identities",
        sa.Column("source_context", postgresql.JSONB()),
    )
    op.create_foreign_key(
        "fk_service_location_source_master_scope",
        "service_location_source_identities",
        "hcp_migration_master_runs",
        ["master_run_id", "company_id", "branch_id"],
        ["id", "company_id", "branch_id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_service_location_source4_lineage_required",
        "service_location_source_identities",
        "source_system <> 'housecall_pro_source4' OR "
        "(branch_id IS NOT NULL AND master_run_id IS NOT NULL AND "
        "source_digest IS NOT NULL AND package_digest IS NOT NULL AND "
        "transformation_version IS NOT NULL AND transformation_digest IS NOT NULL)",
    )

    for column in (
        sa.Column("source_location_id", sa.String(191)),
        sa.Column("parent_customer_source_id", sa.String(191)),
        sa.Column("package_digest", sa.String(64)),
        sa.Column("transformation_digest", sa.String(64)),
        sa.Column("reconciliation_key", sa.String(64)),
        sa.Column(
            "resolution_state",
            sa.String(30),
            nullable=False,
            server_default="unresolved",
        ),
    ):
        op.add_column("customer_migration_child_exceptions", column)


def downgrade() -> None:
    for name in (
        "resolution_state",
        "reconciliation_key",
        "transformation_digest",
        "package_digest",
        "parent_customer_source_id",
        "source_location_id",
    ):
        op.drop_column("customer_migration_child_exceptions", name)
    op.drop_constraint(
        "ck_service_location_source4_lineage_required",
        "service_location_source_identities",
        type_="check",
    )
    op.drop_constraint(
        "fk_service_location_source_master_scope",
        "service_location_source_identities",
        type_="foreignkey",
    )
    for name in (
        "source_context",
        "transformation_digest",
        "transformation_version",
        "package_digest",
        "source_digest",
        "master_run_id",
        "branch_id",
    ):
        op.drop_column("service_location_source_identities", name)
    op.drop_constraint(
        "ck_customer_source4_artifact_master_required",
        "customer_migration_source_artifacts",
        type_="check",
    )
    op.drop_constraint(
        "fk_customer_source_artifact_master_scope",
        "customer_migration_source_artifacts",
        type_="foreignkey",
    )
    for name in (
        "staging_digest",
        "hybrid_admission_digest",
        "package_digest",
        "actor_user_id",
        "master_run_id",
    ):
        op.drop_column("customer_migration_source_artifacts", name)
