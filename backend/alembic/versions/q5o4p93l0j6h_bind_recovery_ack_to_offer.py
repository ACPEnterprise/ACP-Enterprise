"""Bind worker recovery acknowledgements to exact offer lineage.

Revision ID: q5o4p93l0j6h
Revises: p4n3o82k9i5g
"""

from collections.abc import Sequence

from alembic import op

revision: str = "q5o4p93l0j6h"
down_revision: str | Sequence[str] | None = "p4n3o82k9i5g"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OFFER_TABLE = "engineering_controlled_execution_offers"
ACK_TABLE = "engineering_worker_recovery_acknowledgements"
OFFER_BINDING = [
    "company_id",
    "id",
    "command_id",
    "execution_id",
    "lease_id",
    "worker_id",
]
ACK_BINDING = [
    "company_id",
    "offer_id",
    "command_id",
    "execution_id",
    "lease_id",
    "worker_id",
]
OLD_CONSTRAINTS = (
    "engineering_worker_recovery_acknow_company_id_execution_id_fkey",
    "engineering_worker_recovery_acknowled_company_id_worker_id_fkey",
    "engineering_worker_recovery_acknowledg_company_id_lease_id_fkey",
    "engineering_worker_recovery_acknowledgements_command_id_fkey",
    "engineering_worker_recovery_acknowledgements_offer_id_fkey",
)


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_controlled_offers_recovery_binding", OFFER_TABLE, OFFER_BINDING
    )
    for constraint in OLD_CONSTRAINTS:
        op.drop_constraint(constraint, ACK_TABLE, type_="foreignkey")
    op.create_foreign_key(
        "fk_worker_recovery_ack_offer_lineage",
        ACK_TABLE,
        OFFER_TABLE,
        ACK_BINDING,
        OFFER_BINDING,
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_worker_recovery_ack_offer_lineage", ACK_TABLE, type_="foreignkey"
    )
    op.create_foreign_key(
        OLD_CONSTRAINTS[0],
        ACK_TABLE,
        "engineering_executions",
        ["company_id", "execution_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        OLD_CONSTRAINTS[1],
        ACK_TABLE,
        "engineering_workers",
        ["company_id", "worker_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        OLD_CONSTRAINTS[2],
        ACK_TABLE,
        "engineering_worker_leases",
        ["company_id", "lease_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        OLD_CONSTRAINTS[3],
        ACK_TABLE,
        "engineering_commands",
        ["command_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        OLD_CONSTRAINTS[4],
        ACK_TABLE,
        OFFER_TABLE,
        ["offer_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "uq_controlled_offers_recovery_binding", OFFER_TABLE, type_="unique"
    )
