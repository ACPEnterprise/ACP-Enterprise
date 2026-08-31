"""Bind Service Agreement root identities to tenant authority.

Revision ID: r6p5q04m1k7i
Revises: q5o4p93l0j6h
"""

from collections.abc import Sequence

from alembic import op

revision: str = "r6p5q04m1k7i"
down_revision: str | Sequence[str] | None = "q5o4p93l0j6h"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AGREEMENT_TABLE = "service_agreements"
PLAN_TABLE = "service_agreement_plans"


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_agreement_plans_company_id", PLAN_TABLE, ["company_id", "id"]
    )
    op.create_unique_constraint(
        "uq_service_agreements_company_id", AGREEMENT_TABLE, ["company_id", "id"]
    )
    for constraint in (
        "service_agreements_customer_id_fkey",
        "service_agreements_plan_id_fkey",
        "service_agreements_predecessor_agreement_id_fkey",
    ):
        op.drop_constraint(constraint, AGREEMENT_TABLE, type_="foreignkey")
    op.create_foreign_key(
        "fk_service_agreements_customer",
        AGREEMENT_TABLE,
        "customers",
        ["company_id", "customer_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_service_agreements_plan",
        AGREEMENT_TABLE,
        PLAN_TABLE,
        ["company_id", "plan_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_service_agreements_predecessor",
        AGREEMENT_TABLE,
        AGREEMENT_TABLE,
        ["company_id", "predecessor_agreement_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    for constraint in (
        "fk_service_agreements_predecessor",
        "fk_service_agreements_plan",
        "fk_service_agreements_customer",
    ):
        op.drop_constraint(constraint, AGREEMENT_TABLE, type_="foreignkey")
    op.create_foreign_key(
        "service_agreements_customer_id_fkey",
        AGREEMENT_TABLE,
        "customers",
        ["customer_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "service_agreements_plan_id_fkey",
        AGREEMENT_TABLE,
        PLAN_TABLE,
        ["plan_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "service_agreements_predecessor_agreement_id_fkey",
        AGREEMENT_TABLE,
        AGREEMENT_TABLE,
        ["predecessor_agreement_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "uq_service_agreements_company_id", AGREEMENT_TABLE, type_="unique"
    )
    op.drop_constraint("uq_agreement_plans_company_id", PLAN_TABLE, type_="unique")
