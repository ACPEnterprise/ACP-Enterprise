"""create worker control plane

Revision ID: b2d4f6a8c013
Revises: a1c3e5f7b902
Create Date: 2026-07-24
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b2d4f6a8c013"
down_revision: str | None = "a1c3e5f7b902"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_engineering_executions_company_id",
        "engineering_executions",
        ["company_id", "id"],
    )
    op.create_table(
        "engineering_workers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_identifier", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("worker_version", sa.String(length=50), nullable=False),
        sa.Column(
            "capabilities", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("lifecycle_state", sa.String(length=20), nullable=False),
        sa.Column(
            "registered_by_user_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(btrim(provider_identifier)) > 0",
            name="ck_engineering_workers_provider_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(name)) > 0", name="ck_engineering_workers_name_not_blank"
        ),
        sa.CheckConstraint(
            "length(btrim(worker_version)) > 0",
            name="ck_engineering_workers_worker_version_not_blank",
        ),
        sa.CheckConstraint(
            "lifecycle_state IN "
            "('registered','available','leased','offline','disabled')",
            name="ck_engineering_workers_lifecycle_state",
        ),
        sa.CheckConstraint("version >= 1", name="ck_engineering_workers_version"),
        sa.CheckConstraint(
            "updated_at >= registered_at", name="ck_engineering_workers_updated_at"
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_engineering_workers_company",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["registered_by_user_id", "company_id"],
            ["memberships.user_id", "memberships.company_id"],
            name="fk_engineering_workers_registering_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_engineering_workers"),
        sa.UniqueConstraint(
            "company_id",
            "provider_identifier",
            "name",
            name="uq_engineering_workers_company_provider_name",
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_engineering_workers_company_id"
        ),
    )
    op.create_index(
        "ix_engineering_workers_company_state",
        "engineering_workers",
        ["company_id", "lifecycle_state", "registered_at", "id"],
        unique=False,
    )
    op.create_table(
        "engineering_worker_leases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("capability_required", sa.String(length=100), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active','expired','released')",
            name="ck_worker_leases_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_worker_leases_version"),
        sa.CheckConstraint(
            "expires_at > started_at", name="ck_worker_leases_expiration"
        ),
        sa.CheckConstraint(
            "released_at IS NULL OR released_at >= started_at",
            name="ck_worker_leases_released_at",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "execution_id"],
            ["engineering_executions.company_id", "engineering_executions.id"],
            name="fk_worker_leases_execution",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "worker_id"],
            ["engineering_workers.company_id", "engineering_workers.id"],
            name="fk_worker_leases_worker",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_engineering_worker_leases"),
        sa.UniqueConstraint("company_id", "id", name="uq_worker_leases_company_id"),
    )
    op.create_index(
        "ix_worker_leases_company_status_expiration",
        "engineering_worker_leases",
        ["company_id", "status", "expires_at", "id"],
        unique=False,
    )
    op.create_index(
        "uq_worker_leases_active_execution",
        "engineering_worker_leases",
        ["company_id", "execution_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "uq_worker_leases_active_worker",
        "engineering_worker_leases",
        ["company_id", "worker_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_table(
        "engineering_worker_heartbeats",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("health", sa.String(length=20), nullable=False),
        sa.Column("worker_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "health IN ('healthy','degraded','unhealthy')",
            name="ck_worker_heartbeats_health",
        ),
        sa.CheckConstraint("worker_version >= 1", name="ck_worker_heartbeats_version"),
        sa.ForeignKeyConstraint(
            ["company_id", "worker_id"],
            ["engineering_workers.company_id", "engineering_workers.id"],
            name="fk_worker_heartbeats_worker",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_engineering_worker_heartbeats"),
        sa.UniqueConstraint(
            "company_id",
            "worker_id",
            "worker_version",
            name="uq_worker_heartbeats_worker_version",
        ),
    )
    op.create_index(
        "ix_worker_heartbeats_worker_seen",
        "engineering_worker_heartbeats",
        ["company_id", "worker_id", "last_seen", "id"],
        unique=False,
    )
    op.create_table(
        "engineering_worker_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lease_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "validation_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "evidence_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "output_references",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("failure_classification", sa.String(length=50), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status = 'not_executed'", name="ck_worker_results_status"),
        sa.CheckConstraint(
            "failure_classification = 'execution_not_connected'",
            name="ck_worker_results_failure",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "execution_id"],
            ["engineering_executions.company_id", "engineering_executions.id"],
            name="fk_worker_results_execution",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "lease_id"],
            ["engineering_worker_leases.company_id", "engineering_worker_leases.id"],
            name="fk_worker_results_lease",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "worker_id"],
            ["engineering_workers.company_id", "engineering_workers.id"],
            name="fk_worker_results_worker",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_engineering_worker_results"),
        sa.UniqueConstraint(
            "company_id", "lease_id", name="uq_worker_results_company_lease"
        ),
    )
    op.create_index(
        "ix_worker_results_company_execution",
        "engineering_worker_results",
        ["company_id", "execution_id", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_worker_results_company_execution",
        table_name="engineering_worker_results",
    )
    op.drop_table("engineering_worker_results")
    op.drop_index(
        "ix_worker_heartbeats_worker_seen",
        table_name="engineering_worker_heartbeats",
    )
    op.drop_table("engineering_worker_heartbeats")
    op.drop_index(
        "uq_worker_leases_active_worker", table_name="engineering_worker_leases"
    )
    op.drop_index(
        "uq_worker_leases_active_execution", table_name="engineering_worker_leases"
    )
    op.drop_index(
        "ix_worker_leases_company_status_expiration",
        table_name="engineering_worker_leases",
    )
    op.drop_table("engineering_worker_leases")
    op.drop_index(
        "ix_engineering_workers_company_state", table_name="engineering_workers"
    )
    op.drop_table("engineering_workers")
    op.drop_constraint(
        "uq_engineering_executions_company_id",
        "engineering_executions",
        type_="unique",
    )
