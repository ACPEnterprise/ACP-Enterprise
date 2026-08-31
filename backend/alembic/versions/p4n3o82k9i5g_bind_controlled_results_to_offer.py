"""Bind controlled execution results to exact offer authority.

Revision ID: p4n3o82k9i5g
Revises: o3m2n71j8h4f
"""

from collections.abc import Sequence

from alembic import op

revision: str = "p4n3o82k9i5g"
down_revision: str | Sequence[str] | None = "o3m2n71j8h4f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OFFER_TABLE = "engineering_controlled_execution_offers"
RESULT_TABLE = "engineering_controlled_execution_results"
OFFER_BINDING = [
    "company_id",
    "id",
    "command_id",
    "execution_id",
    "lease_id",
    "worker_id",
    "session_id",
]
RESULT_BINDING = [
    "company_id",
    "offer_id",
    "command_id",
    "execution_id",
    "lease_id",
    "worker_id",
    "session_id",
]


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_controlled_offers_result_binding", OFFER_TABLE, OFFER_BINDING
    )
    op.drop_constraint("fk_controlled_results_offer", RESULT_TABLE, type_="foreignkey")
    op.create_foreign_key(
        "fk_controlled_results_offer",
        RESULT_TABLE,
        OFFER_TABLE,
        RESULT_BINDING,
        OFFER_BINDING,
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_controlled_results_offer", RESULT_TABLE, type_="foreignkey")
    op.create_foreign_key(
        "fk_controlled_results_offer",
        RESULT_TABLE,
        OFFER_TABLE,
        ["company_id", "offer_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "uq_controlled_offers_result_binding", OFFER_TABLE, type_="unique"
    )
