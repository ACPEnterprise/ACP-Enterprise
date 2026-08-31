"""Bind review decisions and repository authorizations to exact review authority.

Revision ID: n4m2l50g7e3c
Revises: m3l1k49f6d2b
"""

from collections.abc import Sequence

from alembic import op

revision: str = "n4m2l50g7e3c"
down_revision: str | Sequence[str] | None = "m3l1k49f6d2b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for name, table, columns in (
        (
            "uq_engineering_reviews_authorization_authority",
            "engineering_execution_reviews",
            ["company_id", "id", "command_id", "execution_id", "result_id", "review_digest"],
        ),
        (
            "uq_engineering_reviews_decision_authority",
            "engineering_execution_reviews",
            ["company_id", "id", "review_digest"],
        ),
        (
            "uq_engineering_review_decisions_authorization_authority",
            "engineering_execution_review_decisions",
            ["company_id", "id", "review_id", "review_digest"],
        ),
    ):
        op.create_unique_constraint(name, table, columns)

    op.drop_constraint(
        "fk_engineering_review_decisions_review",
        "engineering_execution_review_decisions",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_engineering_review_decisions_exact_review",
        "engineering_execution_review_decisions",
        "engineering_execution_reviews",
        ["company_id", "review_id", "review_digest"],
        ["company_id", "id", "review_digest"],
        ondelete="RESTRICT",
    )

    for name in (
        "fk_repository_authorizations_review",
        "fk_repository_authorizations_command_company",
        "fk_repository_authorizations_execution_company",
        "fk_repository_authorizations_result_company",
        "fk_repository_authorizations_decision_company",
    ):
        op.drop_constraint(name, "engineering_repository_authorizations", type_="foreignkey")
    op.create_foreign_key(
        "fk_repository_authorizations_exact_review",
        "engineering_repository_authorizations",
        "engineering_execution_reviews",
        ["company_id", "review_id", "command_id", "execution_id", "result_id", "review_digest"],
        ["company_id", "id", "command_id", "execution_id", "result_id", "review_digest"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_repository_authorizations_exact_decision",
        "engineering_repository_authorizations",
        "engineering_execution_review_decisions",
        ["company_id", "review_decision_id", "review_id", "review_digest"],
        ["company_id", "id", "review_id", "review_digest"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_repository_authorizations_exact_decision", "engineering_repository_authorizations", type_="foreignkey")
    op.drop_constraint("fk_repository_authorizations_exact_review", "engineering_repository_authorizations", type_="foreignkey")
    for name, remote_table, column in (
        ("fk_repository_authorizations_review", "engineering_execution_reviews", "review_id"),
        ("fk_repository_authorizations_command_company", "engineering_commands", "command_id"),
        ("fk_repository_authorizations_execution_company", "engineering_executions", "execution_id"),
        ("fk_repository_authorizations_result_company", "engineering_normalized_provider_results", "result_id"),
        ("fk_repository_authorizations_decision_company", "engineering_execution_review_decisions", "review_decision_id"),
    ):
        op.create_foreign_key(name, "engineering_repository_authorizations", remote_table, ["company_id", column], ["company_id", "id"], ondelete="RESTRICT")

    op.drop_constraint("fk_engineering_review_decisions_exact_review", "engineering_execution_review_decisions", type_="foreignkey")
    op.create_foreign_key("fk_engineering_review_decisions_review", "engineering_execution_review_decisions", "engineering_execution_reviews", ["company_id", "review_id"], ["company_id", "id"], ondelete="RESTRICT")
    for name, table in (
        ("uq_engineering_review_decisions_authorization_authority", "engineering_execution_review_decisions"),
        ("uq_engineering_reviews_decision_authority", "engineering_execution_reviews"),
        ("uq_engineering_reviews_authorization_authority", "engineering_execution_reviews"),
    ):
        op.drop_constraint(name, table, type_="unique")
