"""create durable MMQ scheduler reconciliation

Revision ID: u6k8g0c2d497
Revises: t5j7f9b1c386
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "u6k8g0c2d497"
down_revision: str | None = "t5j7f9b1c386"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column("engineering_milestones", sa.Column("milestone_code", sa.String(80)))
    op.add_column(
        "engineering_milestones", sa.Column("scheduler_version", sa.String(80))
    )
    op.add_column(
        "engineering_milestones", sa.Column("scheduler_fingerprint", sa.String(64))
    )
    op.add_column(
        "engineering_milestones", sa.Column("permanent_capacity_identity", sa.String(8))
    )
    op.add_column(
        "engineering_milestones",
        sa.Column("implementation_classification", sa.String(16)),
    )
    op.add_column(
        "engineering_milestones", sa.Column("integration_checkpoint", sa.String(80))
    )
    op.add_column(
        "engineering_milestones", sa.Column("starting_commit_rule", sa.Text())
    )
    op.add_column(
        "engineering_milestones",
        sa.Column(
            "starting_commit_evidence",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "engineering_milestones", sa.Column("migration_classification", sa.String(32))
    )
    op.add_column(
        "engineering_milestones",
        sa.Column("shared_contract_classification", sa.String(32)),
    )
    op.add_column("engineering_milestones", sa.Column("readiness_state", sa.String(32)))
    op.add_column(
        "engineering_milestones",
        sa.Column(
            "dependency_evidence",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "engineering_milestones",
        sa.Column(
            "reconciliation_state",
            sa.String(32),
            nullable=False,
            server_default="legacy_unreconciled",
        ),
    )
    op.create_unique_constraint(
        "uq_engineering_milestone_code",
        "engineering_milestones",
        ["company_id", "milestone_code"],
    )
    op.create_check_constraint(
        "ck_engineering_milestone_reconciliation_state",
        "engineering_milestones",
        "reconciliation_state IN ('current','legacy_unreconciled','superseded','ambiguous','reconciliation_required')",
    )

    op.create_table(
        "engineering_scheduler_snapshots",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("scheduler_version", sa.String(80), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("manifest", JSONB, nullable=False),
        sa.Column("source_documents", JSONB, nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "company_id", "scheduler_version", name="uq_scheduler_snapshot_version"
        ),
        sa.UniqueConstraint(
            "company_id", "fingerprint", name="uq_scheduler_snapshot_fingerprint"
        ),
        sa.CheckConstraint(
            "fingerprint ~ '^[0-9a-f]{64}$'", name="ck_scheduler_snapshot_fingerprint"
        ),
        sa.CheckConstraint("version >= 1", name="ck_scheduler_snapshot_row_version"),
    )
    op.create_index(
        "uq_scheduler_snapshot_active_company",
        "engineering_scheduler_snapshots",
        ["company_id"],
        unique=True,
        postgresql_where=sa.text("active"),
    )
    op.create_table(
        "engineering_permanent_capacities",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("identity_code", sa.String(8), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("reconciliation_reason", sa.String(240)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "company_id", "identity_code", name="uq_permanent_capacity_code"
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_permanent_capacity_company_id"
        ),
        sa.CheckConstraint(
            "identity_code IN ('OM1','OM2','MIG','ECO','LAP')",
            name="ck_permanent_capacity_code",
        ),
        sa.CheckConstraint(
            "state IN ('available','unavailable','reconciliation_required')",
            name="ck_permanent_capacity_state",
        ),
        sa.CheckConstraint("version >= 1", name="ck_permanent_capacity_version"),
    )
    op.create_table(
        "engineering_capacity_bindings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("permanent_capacity_id", UUID, nullable=False),
        sa.Column("worker_capacity_id", UUID, nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("evidence", JSONB, nullable=False),
        sa.Column("bound_by_user_id", UUID),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "permanent_capacity_id"],
            [
                "engineering_permanent_capacities.company_id",
                "engineering_permanent_capacities.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "worker_capacity_id"],
            [
                "engineering_worker_capacities.company_id",
                "engineering_worker_capacities.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["bound_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "state IN ('candidate','active','superseded','reconciliation_required')",
            name="ck_capacity_binding_state",
        ),
        sa.CheckConstraint("version >= 1", name="ck_capacity_binding_version"),
    )
    op.create_index(
        "uq_capacity_binding_active_identity",
        "engineering_capacity_bindings",
        ["company_id", "permanent_capacity_id"],
        unique=True,
        postgresql_where=sa.text("state = 'active'"),
    )
    op.create_table(
        "engineering_scheduler_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("scheduler_version", sa.String(80), nullable=False),
        sa.Column("milestone_code", sa.String(80)),
        sa.Column("permanent_capacity_identity", sa.String(8)),
        sa.Column("record_id", UUID),
        sa.Column("details", JSONB, nullable=False),
        sa.Column("actor_user_id", UUID),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_scheduler_event_idempotency"
        ),
    )
    op.create_index(
        "ix_scheduler_event_company_time",
        "engineering_scheduler_events",
        ["company_id", "occurred_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scheduler_event_company_time", table_name="engineering_scheduler_events"
    )
    op.drop_table("engineering_scheduler_events")
    op.drop_index(
        "uq_capacity_binding_active_identity",
        table_name="engineering_capacity_bindings",
    )
    op.drop_table("engineering_capacity_bindings")
    op.drop_table("engineering_permanent_capacities")
    op.drop_index(
        "uq_scheduler_snapshot_active_company",
        table_name="engineering_scheduler_snapshots",
    )
    op.drop_table("engineering_scheduler_snapshots")
    op.drop_constraint(
        "ck_engineering_milestone_reconciliation_state",
        "engineering_milestones",
        type_="check",
    )
    op.drop_constraint(
        "uq_engineering_milestone_code", "engineering_milestones", type_="unique"
    )
    for column in (
        "reconciliation_state",
        "dependency_evidence",
        "readiness_state",
        "shared_contract_classification",
        "migration_classification",
        "starting_commit_evidence",
        "starting_commit_rule",
        "integration_checkpoint",
        "implementation_classification",
        "permanent_capacity_identity",
        "scheduler_fingerprint",
        "scheduler_version",
        "milestone_code",
    ):
        op.drop_column("engineering_milestones", column)
