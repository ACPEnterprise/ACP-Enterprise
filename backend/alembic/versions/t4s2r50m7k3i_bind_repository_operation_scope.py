"""Bind repository operations to exact authorization authority.

Revision ID: t4s2r50m7k3i
Revises: s3r1q49l6j2h
"""

from collections.abc import Sequence

from alembic import op

revision: str = "t4s2r50m7k3i"
down_revision: str | Sequence[str] | None = "s3r1q49l6j2h"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_repository_authorizations_operation_scope",
        "engineering_repository_authorizations",
        [
            "company_id",
            "id",
            "command_id",
            "execution_id",
            "review_decision_id",
        ],
    )
    op.drop_constraint(
        "fk_repository_operations_authorization",
        "engineering_repository_operations",
        type_="foreignkey",
    )
    for name in (
        "engineering_repository_operations_command_id_fkey",
        "engineering_repository_operations_execution_id_fkey",
        "engineering_repository_operations_review_decision_id_fkey",
    ):
        op.drop_constraint(
            name, "engineering_repository_operations", type_="foreignkey"
        )
    op.create_foreign_key(
        "fk_repository_operations_authorization_scope",
        "engineering_repository_operations",
        "engineering_repository_authorizations",
        [
            "company_id",
            "authorization_id",
            "command_id",
            "execution_id",
            "review_decision_id",
        ],
        [
            "company_id",
            "id",
            "command_id",
            "execution_id",
            "review_decision_id",
        ],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_repository_operations_authorization_scope",
        "engineering_repository_operations",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_repository_operations_authorization",
        "engineering_repository_operations",
        "engineering_repository_authorizations",
        ["company_id", "authorization_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    for name, column, parent in (
        (
            "engineering_repository_operations_command_id_fkey",
            "command_id",
            "engineering_commands",
        ),
        (
            "engineering_repository_operations_execution_id_fkey",
            "execution_id",
            "engineering_executions",
        ),
        (
            "engineering_repository_operations_review_decision_id_fkey",
            "review_decision_id",
            "engineering_execution_review_decisions",
        ),
    ):
        op.create_foreign_key(
            name,
            "engineering_repository_operations",
            parent,
            [column],
            ["id"],
            ondelete="RESTRICT",
        )
    op.drop_constraint(
        "uq_repository_authorizations_operation_scope",
        "engineering_repository_authorizations",
        type_="unique",
    )
