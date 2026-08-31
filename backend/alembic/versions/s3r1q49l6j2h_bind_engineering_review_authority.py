"""Bind Engineering review and repository authorization tenant authority.

Revision ID: s3r1q49l6j2h
Revises: r2q0p38k5i1g
"""

from collections.abc import Sequence

from alembic import op

revision: str = "s3r1q49l6j2h"
down_revision: str | Sequence[str] | None = "r2q0p38k5i1g"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _replace_fk(
    table: str,
    old_name: str,
    new_name: str,
    columns: list[str],
    parent: str,
) -> None:
    op.drop_constraint(old_name, table, type_="foreignkey")
    op.create_foreign_key(
        new_name,
        table,
        parent,
        ["company_id", *columns],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )


def _restore_fk(
    table: str,
    scoped_name: str,
    old_name: str,
    column: str,
    parent: str,
) -> None:
    op.drop_constraint(scoped_name, table, type_="foreignkey")
    op.create_foreign_key(
        old_name,
        table,
        parent,
        [column],
        ["id"],
        ondelete="RESTRICT",
    )


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_normalized_results_company_id",
        "engineering_normalized_provider_results",
        ["company_id", "id"],
    )
    op.create_unique_constraint(
        "uq_engineering_review_decisions_company_id",
        "engineering_execution_review_decisions",
        ["company_id", "id"],
    )

    for old_name, new_name, column, parent in (
        (
            "engineering_execution_reviews_command_id_fkey",
            "fk_engineering_reviews_command_company",
            "command_id",
            "engineering_commands",
        ),
        (
            "engineering_execution_reviews_execution_id_fkey",
            "fk_engineering_reviews_execution_company",
            "execution_id",
            "engineering_executions",
        ),
        (
            "engineering_execution_reviews_composition_id_fkey",
            "fk_engineering_reviews_composition_company",
            "composition_id",
            "engineering_execution_compositions",
        ),
        (
            "engineering_execution_reviews_attempt_id_fkey",
            "fk_engineering_reviews_attempt_company",
            "attempt_id",
            "engineering_provider_execution_attempts",
        ),
        (
            "engineering_execution_reviews_result_id_fkey",
            "fk_engineering_reviews_result_company",
            "result_id",
            "engineering_normalized_provider_results",
        ),
        (
            "fk_engineering_execution_reviews_controlled_result",
            "fk_engineering_reviews_controlled_result_company",
            "controlled_result_id",
            "engineering_controlled_execution_results",
        ),
    ):
        _replace_fk(
            "engineering_execution_reviews", old_name, new_name, [column], parent
        )

    for old_name, new_name, column, parent in (
        (
            "engineering_repository_authorizations_command_id_fkey",
            "fk_repository_authorizations_command_company",
            "command_id",
            "engineering_commands",
        ),
        (
            "engineering_repository_authorizations_execution_id_fkey",
            "fk_repository_authorizations_execution_company",
            "execution_id",
            "engineering_executions",
        ),
        (
            "engineering_repository_authorizations_result_id_fkey",
            "fk_repository_authorizations_result_company",
            "result_id",
            "engineering_normalized_provider_results",
        ),
        (
            "engineering_repository_authorizations_review_decision_id_fkey",
            "fk_repository_authorizations_decision_company",
            "review_decision_id",
            "engineering_execution_review_decisions",
        ),
    ):
        _replace_fk(
            "engineering_repository_authorizations",
            old_name,
            new_name,
            [column],
            parent,
        )


def downgrade() -> None:
    for scoped_name, old_name, column, parent in (
        (
            "fk_repository_authorizations_decision_company",
            "engineering_repository_authorizations_review_decision_id_fkey",
            "review_decision_id",
            "engineering_execution_review_decisions",
        ),
        (
            "fk_repository_authorizations_result_company",
            "engineering_repository_authorizations_result_id_fkey",
            "result_id",
            "engineering_normalized_provider_results",
        ),
        (
            "fk_repository_authorizations_execution_company",
            "engineering_repository_authorizations_execution_id_fkey",
            "execution_id",
            "engineering_executions",
        ),
        (
            "fk_repository_authorizations_command_company",
            "engineering_repository_authorizations_command_id_fkey",
            "command_id",
            "engineering_commands",
        ),
    ):
        _restore_fk(
            "engineering_repository_authorizations",
            scoped_name,
            old_name,
            column,
            parent,
        )

    for scoped_name, old_name, column, parent in (
        (
            "fk_engineering_reviews_controlled_result_company",
            "fk_engineering_execution_reviews_controlled_result",
            "controlled_result_id",
            "engineering_controlled_execution_results",
        ),
        (
            "fk_engineering_reviews_result_company",
            "engineering_execution_reviews_result_id_fkey",
            "result_id",
            "engineering_normalized_provider_results",
        ),
        (
            "fk_engineering_reviews_attempt_company",
            "engineering_execution_reviews_attempt_id_fkey",
            "attempt_id",
            "engineering_provider_execution_attempts",
        ),
        (
            "fk_engineering_reviews_composition_company",
            "engineering_execution_reviews_composition_id_fkey",
            "composition_id",
            "engineering_execution_compositions",
        ),
        (
            "fk_engineering_reviews_execution_company",
            "engineering_execution_reviews_execution_id_fkey",
            "execution_id",
            "engineering_executions",
        ),
        (
            "fk_engineering_reviews_command_company",
            "engineering_execution_reviews_command_id_fkey",
            "command_id",
            "engineering_commands",
        ),
    ):
        _restore_fk(
            "engineering_execution_reviews",
            scoped_name,
            old_name,
            column,
            parent,
        )

    op.drop_constraint(
        "uq_engineering_review_decisions_company_id",
        "engineering_execution_review_decisions",
        type_="unique",
    )
    op.drop_constraint(
        "uq_normalized_results_company_id",
        "engineering_normalized_provider_results",
        type_="unique",
    )
