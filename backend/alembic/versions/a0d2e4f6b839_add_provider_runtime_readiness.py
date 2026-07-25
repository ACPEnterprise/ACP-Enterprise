"""add provider runtime readiness

Revision ID: a0d2e4f6b839
Revises: f9c1d3e5a728
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a0d2e4f6b839"
down_revision: str | None = "f9c1d3e5a728"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "engineering_provider_sessions",
        sa.Column(
            "runtime_state",
            sa.String(length=40),
            nullable=False,
            server_default="created",
        ),
    )
    op.add_column(
        "engineering_provider_sessions",
        sa.Column(
            "credential_status",
            sa.String(length=20),
            nullable=False,
            server_default="unavailable",
        ),
    )
    op.add_column(
        "engineering_provider_sessions",
        sa.Column(
            "provider_ready",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "engineering_provider_sessions",
        sa.Column("provider_session_reference", sa.String(length=200)),
    )
    op.create_check_constraint(
        "ck_provider_sessions_runtime_state",
        "engineering_provider_sessions",
        "runtime_state IN ('created','initializing','credential_validation',"
        "'provider_initializing','provider_ready','opening','ready','active',"
        "'closing','closed','recovering','failed','cancelled',"
        "'credential_failure','provider_failure','timeout')",
    )
    op.create_check_constraint(
        "ck_provider_sessions_credential_status",
        "engineering_provider_sessions",
        "credential_status IN ('unavailable','invalid','expired','usable')",
    )
    op.create_check_constraint(
        "ck_provider_sessions_provider_ready",
        "engineering_provider_sessions",
        "provider_ready = false OR "
        "(runtime_state = 'provider_ready' AND credential_status = 'usable' "
        "AND provider_session_reference IS NOT NULL)",
    )
    op.alter_column(
        "engineering_provider_sessions", "runtime_state", server_default=None
    )
    op.alter_column(
        "engineering_provider_sessions", "credential_status", server_default=None
    )
    op.alter_column(
        "engineering_provider_sessions", "provider_ready", server_default=None
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_provider_sessions_provider_ready",
        "engineering_provider_sessions",
        type_="check",
    )
    op.drop_constraint(
        "ck_provider_sessions_credential_status",
        "engineering_provider_sessions",
        type_="check",
    )
    op.drop_constraint(
        "ck_provider_sessions_runtime_state",
        "engineering_provider_sessions",
        type_="check",
    )
    op.drop_column("engineering_provider_sessions", "provider_session_reference")
    op.drop_column("engineering_provider_sessions", "provider_ready")
    op.drop_column("engineering_provider_sessions", "credential_status")
    op.drop_column("engineering_provider_sessions", "runtime_state")
