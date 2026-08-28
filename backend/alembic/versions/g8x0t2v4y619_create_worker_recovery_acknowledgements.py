"""create audited worker recovery acknowledgements

Revision ID: g8x0t2v4y619
Revises: f7w9s1u3x508
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "g8x0t2v4y619"
down_revision: str | Sequence[str] | None = "f7w9s1u3x508"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "engineering_worker_recovery_acknowledgements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("offer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lease_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("journal_digest", sa.String(64), nullable=False),
        sa.Column("reconciliation_reason", sa.String(200), nullable=False),
        sa.Column("acknowledgement_reason", sa.String(500), nullable=False),
        sa.Column("operator_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("authorization_context", postgresql.JSONB(), nullable=False),
        sa.Column("acknowledgement_version", sa.Integer(), nullable=False),
        sa.Column("audit_digest", sa.String(64), nullable=False),
        sa.Column("historical_execution_unresolved", sa.Boolean(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.Column("local_archive_digest", sa.String(64)),
        sa.Column("active_block_released", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "acknowledgement_version >= 1", name="ck_worker_recovery_ack_version"
        ),
        sa.CheckConstraint(
            "length(journal_digest) = 64", name="ck_worker_recovery_ack_journal_digest"
        ),
        sa.CheckConstraint(
            "length(audit_digest) = 64", name="ck_worker_recovery_ack_audit_digest"
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["operator_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["command_id"], ["engineering_commands.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["offer_id"],
            ["engineering_controlled_execution_offers.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "worker_id"],
            ["engineering_workers.company_id", "engineering_workers.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "lease_id"],
            ["engineering_worker_leases.company_id", "engineering_worker_leases.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "execution_id"],
            ["engineering_executions.company_id", "engineering_executions.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "company_id",
            "worker_id",
            "journal_digest",
            name="uq_worker_recovery_ack_journal",
        ),
        sa.UniqueConstraint(
            "company_id", "audit_digest", name="uq_worker_recovery_ack_audit"
        ),
    )
    op.create_index(
        "ix_worker_recovery_ack_pending",
        "engineering_worker_recovery_acknowledgements",
        ["company_id", "worker_id", "applied_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_worker_recovery_ack_pending",
        table_name="engineering_worker_recovery_acknowledgements",
    )
    op.drop_table("engineering_worker_recovery_acknowledgements")
