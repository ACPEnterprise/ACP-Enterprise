"""Bind Engineering reviews to exact provider or controlled result lineage.

Revision ID: m3l1k49f6d2b
Revises: l2k0j38e5c1a
"""

from collections.abc import Sequence

from alembic import op

revision: str = "m3l1k49f6d2b"
down_revision: str | Sequence[str] | None = "l2k0j38e5c1a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for name, table, columns in (
        (
            "uq_execution_compositions_review_authority",
            "engineering_execution_compositions",
            ["company_id", "id", "execution_id", "command_id"],
        ),
        (
            "uq_normalized_results_review_authority",
            "engineering_normalized_provider_results",
            ["company_id", "id", "attempt_id", "composition_id"],
        ),
        (
            "uq_controlled_results_review_authority",
            "engineering_controlled_execution_results",
            ["company_id", "id", "execution_id", "command_id"],
        ),
    ):
        op.create_unique_constraint(name, table, columns)

    for name in (
        "fk_engineering_reviews_execution_company",
        "fk_engineering_reviews_composition_company",
        "fk_engineering_reviews_attempt_company",
        "fk_engineering_reviews_result_company",
        "fk_engineering_reviews_controlled_result_company",
    ):
        op.drop_constraint(name, "engineering_execution_reviews", type_="foreignkey")

    for name, remote_table, local, remote in (
        (
            "fk_engineering_reviews_exact_execution",
            "engineering_executions",
            ["company_id", "execution_id", "command_id"],
            ["company_id", "id", "command_id"],
        ),
        (
            "fk_engineering_reviews_exact_composition",
            "engineering_execution_compositions",
            ["company_id", "composition_id", "execution_id", "command_id"],
            ["company_id", "id", "execution_id", "command_id"],
        ),
        (
            "fk_engineering_reviews_exact_attempt",
            "engineering_provider_execution_attempts",
            ["company_id", "attempt_id", "composition_id"],
            ["company_id", "id", "composition_id"],
        ),
        (
            "fk_engineering_reviews_exact_result",
            "engineering_normalized_provider_results",
            ["company_id", "result_id", "attempt_id", "composition_id"],
            ["company_id", "id", "attempt_id", "composition_id"],
        ),
        (
            "fk_engineering_reviews_exact_controlled_result",
            "engineering_controlled_execution_results",
            ["company_id", "controlled_result_id", "execution_id", "command_id"],
            ["company_id", "id", "execution_id", "command_id"],
        ),
    ):
        op.create_foreign_key(
            name,
            "engineering_execution_reviews",
            remote_table,
            local,
            remote,
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    for name in (
        "fk_engineering_reviews_exact_controlled_result",
        "fk_engineering_reviews_exact_result",
        "fk_engineering_reviews_exact_attempt",
        "fk_engineering_reviews_exact_composition",
        "fk_engineering_reviews_exact_execution",
    ):
        op.drop_constraint(name, "engineering_execution_reviews", type_="foreignkey")

    for name, remote_table, column in (
        ("fk_engineering_reviews_execution_company", "engineering_executions", "execution_id"),
        ("fk_engineering_reviews_composition_company", "engineering_execution_compositions", "composition_id"),
        ("fk_engineering_reviews_attempt_company", "engineering_provider_execution_attempts", "attempt_id"),
        ("fk_engineering_reviews_result_company", "engineering_normalized_provider_results", "result_id"),
        ("fk_engineering_reviews_controlled_result_company", "engineering_controlled_execution_results", "controlled_result_id"),
    ):
        op.create_foreign_key(
            name,
            "engineering_execution_reviews",
            remote_table,
            ["company_id", column],
            ["company_id", "id"],
            ondelete="RESTRICT",
        )

    for name, table in (
        ("uq_controlled_results_review_authority", "engineering_controlled_execution_results"),
        ("uq_normalized_results_review_authority", "engineering_normalized_provider_results"),
        ("uq_execution_compositions_review_authority", "engineering_execution_compositions"),
    ):
        op.drop_constraint(name, table, type_="unique")
