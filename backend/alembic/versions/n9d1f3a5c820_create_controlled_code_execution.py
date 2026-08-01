"""Create controlled code execution boundaries and node evidence.

Revision ID: n9d1f3a5c820
Revises: m8c0e2f4b719
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "n9d1f3a5c820"
down_revision: str | None = "m8c0e2f4b719"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "engineering_commands",
        sa.Column("execution_boundary", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "engineering_commands",
        sa.Column("execution_boundary_digest", sa.String(64), nullable=True),
    )
    op.execute(
        "UPDATE engineering_commands SET execution_boundary = jsonb_build_object('allowed_repository',repository_key,'allowed_branch',expected_branch,'expected_head',expected_head,'allowed_paths',jsonb_build_array(),'forbidden_paths',jsonb_build_array('.git/**','.env*','**/.env*'),'permitted_operations',jsonb_build_array('inspect'),'validation_requirements',jsonb_build_array()), execution_boundary_digest = repeat('0',64)"
    )
    op.alter_column("engineering_commands", "execution_boundary", nullable=False)
    op.alter_column("engineering_commands", "execution_boundary_digest", nullable=False)
    op.drop_constraint(
        "ck_controlled_offers_command_type",
        "engineering_controlled_execution_offers",
        type_="check",
    )
    op.create_check_constraint(
        "ck_controlled_offers_command_type",
        "engineering_controlled_execution_offers",
        "command_type IN ('inspect_workspace','execute_code')",
    )
    op.drop_constraint(
        "ck_controlled_results_repository_immutable",
        "engineering_controlled_execution_results",
        type_="check",
    )
    op.create_check_constraint(
        "ck_controlled_results_repository_mutation_boolean",
        "engineering_controlled_execution_results",
        "repository_mutated IN (true,false)",
    )
    op.create_table(
        "engineering_execution_nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "worker_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("engineering_workers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("provider_identifier", sa.String(100), nullable=False),
        sa.Column("credential_fingerprint", sa.String(64), nullable=False),
        sa.Column("capabilities", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_authenticated_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('active','revoked','expired')", name="ck_execution_nodes_status"
        ),
        sa.CheckConstraint("version >= 1", name="ck_execution_nodes_version"),
        sa.UniqueConstraint(
            "company_id", "worker_id", name="uq_execution_nodes_worker"
        ),
        sa.UniqueConstraint(
            "company_id", "credential_fingerprint", name="uq_execution_nodes_credential"
        ),
    )
    op.create_index(
        "ix_execution_nodes_company_status",
        "engineering_execution_nodes",
        ["company_id", "status"],
    )
    op.create_table(
        "engineering_provider_execution_transitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "node_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("engineering_execution_nodes.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "command_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("engineering_commands.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "execution_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("engineering_executions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "lease_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("engineering_worker_leases.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("phase", sa.String(32), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "phase IN ('queued','composed','workspace_ready','executing','validating','commit_ready','publishing_result','completed','failed','cancelled','reconciliation_required')",
            name="ck_provider_execution_transition_phase",
        ),
        sa.UniqueConstraint(
            "company_id",
            "execution_id",
            "sequence",
            name="uq_provider_execution_transition_sequence",
        ),
    )
    op.create_index(
        "ix_provider_execution_transition_execution",
        "engineering_provider_execution_transitions",
        ["company_id", "execution_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_table("engineering_provider_execution_transitions")
    op.drop_table("engineering_execution_nodes")
    op.drop_column("engineering_commands", "execution_boundary_digest")
    op.drop_column("engineering_commands", "execution_boundary")
    op.drop_constraint(
        "ck_controlled_results_repository_mutation_boolean",
        "engineering_controlled_execution_results",
        type_="check",
    )
    op.create_check_constraint(
        "ck_controlled_results_repository_immutable",
        "engineering_controlled_execution_results",
        "repository_mutated = false",
    )
    op.drop_constraint(
        "ck_controlled_offers_command_type",
        "engineering_controlled_execution_offers",
        type_="check",
    )
    op.create_check_constraint(
        "ck_controlled_offers_command_type",
        "engineering_controlled_execution_offers",
        "command_type = 'inspect_workspace'",
    )
