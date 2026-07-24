"""bind worker identity to orchestration worker

Revision ID: d5f7a9c1e326
Revises: c4e6a8b0d215
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "d5f7a9c1e326"
down_revision: str | None = "c4e6a8b0d215"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "worker_identities",
        sa.Column(
            "orchestration_worker_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_worker_identities_orchestration_worker",
        "worker_identities",
        "engineering_workers",
        ["company_id", "orchestration_worker_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_worker_identities_orchestration_worker",
        "worker_identities",
        ["company_id", "orchestration_worker_id"],
    )
    op.create_unique_constraint(
        "uq_worker_credentials_identity_id",
        "worker_identity_credentials",
        ["company_id", "identity_id", "id"],
    )
    op.add_column(
        "engineering_worker_transport_sessions",
        sa.Column(
            "worker_identity_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
    )
    op.add_column(
        "engineering_worker_transport_sessions",
        sa.Column("credential_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "engineering_worker_transport_sessions",
        sa.Column("credential_version", sa.Integer(), nullable=True),
    )
    # Pre-DF.7 sessions cannot be proven to a specific credential. Preserve
    # their evidence but make them unusable rather than guessing a binding.
    op.execute(
        "UPDATE engineering_worker_transport_sessions "
        "SET state = 'revoked', version = version + 1"
    )
    op.create_check_constraint(
        "ck_worker_transport_sessions_credential_version",
        "engineering_worker_transport_sessions",
        "credential_version IS NULL OR credential_version >= 1",
    )
    op.create_check_constraint(
        "ck_worker_transport_sessions_identity_binding",
        "engineering_worker_transport_sessions",
        "(worker_identity_id IS NOT NULL AND credential_id IS NOT NULL "
        "AND credential_version IS NOT NULL) OR "
        "(state = 'revoked' AND worker_identity_id IS NULL "
        "AND credential_id IS NULL AND credential_version IS NULL)",
    )
    op.create_foreign_key(
        "fk_worker_transport_sessions_identity",
        "engineering_worker_transport_sessions",
        "worker_identities",
        ["company_id", "worker_identity_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_worker_transport_sessions_credential",
        "engineering_worker_transport_sessions",
        "worker_identity_credentials",
        ["company_id", "worker_identity_id", "credential_id"],
        ["company_id", "identity_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_worker_transport_sessions_credential",
        "engineering_worker_transport_sessions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_worker_transport_sessions_identity",
        "engineering_worker_transport_sessions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_worker_transport_sessions_identity_binding",
        "engineering_worker_transport_sessions",
        type_="check",
    )
    op.drop_constraint(
        "ck_worker_transport_sessions_credential_version",
        "engineering_worker_transport_sessions",
        type_="check",
    )
    op.drop_column("engineering_worker_transport_sessions", "credential_version")
    op.drop_column("engineering_worker_transport_sessions", "credential_id")
    op.drop_column("engineering_worker_transport_sessions", "worker_identity_id")
    op.drop_constraint(
        "uq_worker_credentials_identity_id",
        "worker_identity_credentials",
        type_="unique",
    )
    op.drop_constraint(
        "uq_worker_identities_orchestration_worker",
        "worker_identities",
        type_="unique",
    )
    op.drop_constraint(
        "fk_worker_identities_orchestration_worker",
        "worker_identities",
        type_="foreignkey",
    )
    op.drop_column("worker_identities", "orchestration_worker_id")
