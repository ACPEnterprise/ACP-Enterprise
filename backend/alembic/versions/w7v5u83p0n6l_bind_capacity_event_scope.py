"""Bind Engineering capacity events to tenant parent authority.

Revision ID: w7v5u83p0n6l
Revises: v6u4t72o9m5k
"""

from collections.abc import Sequence

from alembic import op

revision: str = "w7v5u83p0n6l"
down_revision: str | Sequence[str] | None = "v6u4t72o9m5k"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PARENTS = (
    ("policy_id", "engineering_capacity_policies", "policy_company"),
    (
        "worker_capacity_id",
        "engineering_worker_capacities",
        "worker_capacity_company",
    ),
    ("reservation_id", "engineering_capacity_reservations", "reservation_company"),
    ("allocation_id", "engineering_capacity_allocations", "allocation_company"),
)


def upgrade() -> None:
    for column, parent, suffix in PARENTS:
        op.drop_constraint(
            f"engineering_capacity_events_{column}_fkey",
            "engineering_capacity_events",
            type_="foreignkey",
        )
        op.create_foreign_key(
            f"fk_capacity_events_{suffix}",
            "engineering_capacity_events",
            parent,
            ["company_id", column],
            ["company_id", "id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    for column, parent, suffix in reversed(PARENTS):
        op.drop_constraint(
            f"fk_capacity_events_{suffix}",
            "engineering_capacity_events",
            type_="foreignkey",
        )
        op.create_foreign_key(
            f"engineering_capacity_events_{column}_fkey",
            "engineering_capacity_events",
            parent,
            [column],
            ["id"],
            ondelete="RESTRICT",
        )
