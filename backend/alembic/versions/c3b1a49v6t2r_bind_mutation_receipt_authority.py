"""Bind Platform mutation receipts to tenant authority.

Revision ID: c3b1a49v6t2r
Revises: b2a0z38u5s1q
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c3b1a49v6t2r"
down_revision: str | Sequence[str] | None = "b2a0z38u5s1q"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_platform_mutation_receipts_company",
        "platform_mutation_receipts",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_platform_mutation_receipts_branch_scope",
        "platform_mutation_receipts",
        "branches",
        ["company_id", "branch_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_platform_mutation_receipts_actor",
        "platform_mutation_receipts",
        "users",
        ["actor_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_platform_mutation_receipts_request_digest",
        "platform_mutation_receipts",
        "length(request_digest) = 64",
    )
    op.create_check_constraint(
        "ck_platform_mutation_receipts_response_status",
        "platform_mutation_receipts",
        "response_status IS NULL OR response_status BETWEEN 100 AND 599",
    )
    op.create_check_constraint(
        "ck_platform_mutation_receipts_completed_result",
        "platform_mutation_receipts",
        "state <> 'completed' OR (result_type IS NOT NULL AND result_id IS NOT NULL "
        "AND response_status IS NOT NULL AND completed_at IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_platform_mutation_receipts_completed_result",
        "platform_mutation_receipts",
        type_="check",
    )
    op.drop_constraint(
        "ck_platform_mutation_receipts_response_status",
        "platform_mutation_receipts",
        type_="check",
    )
    op.drop_constraint(
        "ck_platform_mutation_receipts_request_digest",
        "platform_mutation_receipts",
        type_="check",
    )
    op.drop_constraint(
        "fk_platform_mutation_receipts_actor",
        "platform_mutation_receipts",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_platform_mutation_receipts_branch_scope",
        "platform_mutation_receipts",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_platform_mutation_receipts_company",
        "platform_mutation_receipts",
        type_="foreignkey",
    )
