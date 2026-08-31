"""Bind Service Agreement plans to optional Branch authority.

Revision ID: b2a0z38u5s1q
Revises: a1z9y27t4r0p
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b2a0z38u5s1q"
down_revision: str | Sequence[str] | None = "a1z9y27t4r0p"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_agreement_plans_branch_scope",
        "service_agreement_plans",
        "branches",
        ["company_id", "branch_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_agreement_plans_branch_scope",
        "service_agreement_plans",
        type_="foreignkey",
    )
