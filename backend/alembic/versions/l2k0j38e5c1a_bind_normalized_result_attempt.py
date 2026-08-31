"""Bind normalized provider results to their exact attempt composition.

Revision ID: l2k0j38e5c1a
Revises: k1j9i27d4b0z
"""

from collections.abc import Sequence

from alembic import op

revision: str = "l2k0j38e5c1a"
down_revision: str | Sequence[str] | None = "k1j9i27d4b0z"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_provider_attempts_result_authority",
        "engineering_provider_execution_attempts",
        ["company_id", "id", "composition_id"],
    )
    op.drop_constraint(
        "fk_normalized_results_attempt",
        "engineering_normalized_provider_results",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_normalized_results_composition",
        "engineering_normalized_provider_results",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_normalized_results_exact_attempt",
        "engineering_normalized_provider_results",
        "engineering_provider_execution_attempts",
        ["company_id", "attempt_id", "composition_id"],
        ["company_id", "id", "composition_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_normalized_results_exact_attempt",
        "engineering_normalized_provider_results",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_normalized_results_composition",
        "engineering_normalized_provider_results",
        "engineering_execution_compositions",
        ["company_id", "composition_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "uq_provider_attempts_result_authority",
        "engineering_provider_execution_attempts",
        type_="unique",
    )
    op.create_foreign_key(
        "fk_normalized_results_attempt",
        "engineering_normalized_provider_results",
        "engineering_provider_execution_attempts",
        ["company_id", "attempt_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
