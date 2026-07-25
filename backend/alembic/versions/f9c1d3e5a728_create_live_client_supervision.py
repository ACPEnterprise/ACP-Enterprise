"""create live client supervision

Revision ID: f9c1d3e5a728
Revises: e7a9c1d3f526
Create Date: 2026-07-25
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f9c1d3e5a728"
down_revision: str | None = "e7a9c1d3f526"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "engineering_live_client_supervisors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("recovered_at", sa.DateTime(timezone=True)),
        sa.Column("last_transition_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failure_classification", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "worker_id"],
            ["engineering_workers.company_id", "engineering_workers.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "state IN ('stopped','starting','ready','recovering','reconnecting',"
            "'timed_out','cancelled','failed')",
            name="ck_live_client_supervisors_state",
        ),
        sa.CheckConstraint("version >= 1", name="ck_live_client_supervisors_version"),
        sa.UniqueConstraint(
            "company_id", "worker_id", name="uq_live_client_supervisors_worker"
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_live_client_supervisors_company_id"
        ),
    )
    op.create_index(
        "ix_live_client_supervisors_company_state",
        "engineering_live_client_supervisors",
        ["company_id", "state", "updated_at"],
    )
    op.create_table(
        "engineering_provider_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supervisor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("composition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lease_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_identifier", sa.String(100), nullable=False),
        sa.Column(
            "effective_capabilities",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("approved_code_changes", sa.Boolean(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opening_at", sa.DateTime(timezone=True)),
        sa.Column("ready_at", sa.DateTime(timezone=True)),
        sa.Column("active_at", sa.DateTime(timezone=True)),
        sa.Column("closing_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failure_classification", sa.String(100)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "supervisor_id"],
            [
                "engineering_live_client_supervisors.company_id",
                "engineering_live_client_supervisors.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "composition_id"],
            [
                "engineering_execution_compositions.company_id",
                "engineering_execution_compositions.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "attempt_id"],
            [
                "engineering_provider_execution_attempts.company_id",
                "engineering_provider_execution_attempts.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "state IN ('created','opening','ready','active','closing','closed',"
            "'expired','failed','cancelled')",
            name="ck_provider_sessions_state",
        ),
        sa.CheckConstraint("version >= 1", name="ck_provider_sessions_version"),
        sa.CheckConstraint(
            "expires_at > created_at", name="ck_provider_sessions_expiration"
        ),
        sa.UniqueConstraint(
            "company_id",
            "composition_id",
            "attempt_id",
            name="uq_provider_sessions_composition_attempt",
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_provider_sessions_company_id"),
    )
    op.create_index(
        "ix_provider_sessions_company_state",
        "engineering_provider_sessions",
        ["company_id", "state", "updated_at"],
    )
    op.create_index(
        "ix_provider_sessions_company_composition",
        "engineering_provider_sessions",
        ["company_id", "composition_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_provider_sessions_company_composition",
        table_name="engineering_provider_sessions",
    )
    op.drop_index(
        "ix_provider_sessions_company_state",
        table_name="engineering_provider_sessions",
    )
    op.drop_table("engineering_provider_sessions")
    op.drop_index(
        "ix_live_client_supervisors_company_state",
        table_name="engineering_live_client_supervisors",
    )
    op.drop_table("engineering_live_client_supervisors")
