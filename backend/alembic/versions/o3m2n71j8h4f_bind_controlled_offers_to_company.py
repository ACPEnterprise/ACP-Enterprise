"""Bind controlled execution offer identities to Company authority.

Revision ID: o3m2n71j8h4f
Revises: n2l1j60i7g3e
"""

from collections.abc import Sequence

from alembic import op

revision: str = "o3m2n71j8h4f"
down_revision: str | Sequence[str] | None = "n2l1j60i7g3e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "engineering_controlled_execution_offers"


def upgrade() -> None:
    op.drop_constraint(
        "engineering_controlled_execution_offers_command_id_fkey",
        TABLE,
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_controlled_offers_command",
        TABLE,
        "engineering_commands",
        ["company_id", "command_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_controlled_offers_lease",
        TABLE,
        "engineering_worker_leases",
        ["company_id", "lease_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_controlled_offers_worker",
        TABLE,
        "engineering_workers",
        ["company_id", "worker_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_controlled_offers_session",
        TABLE,
        "engineering_worker_transport_sessions",
        ["company_id", "session_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_controlled_offers_session", TABLE, type_="foreignkey")
    op.drop_constraint("fk_controlled_offers_worker", TABLE, type_="foreignkey")
    op.drop_constraint("fk_controlled_offers_lease", TABLE, type_="foreignkey")
    op.drop_constraint("fk_controlled_offers_command", TABLE, type_="foreignkey")
    op.create_foreign_key(
        "engineering_controlled_execution_offers_command_id_fkey",
        TABLE,
        "engineering_commands",
        ["command_id"],
        ["id"],
        ondelete="RESTRICT",
    )
