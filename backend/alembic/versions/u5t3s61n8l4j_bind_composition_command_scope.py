"""Bind execution compositions to exact execution command authority.

Revision ID: u5t3s61n8l4j
Revises: t4s2r50m7k3i
"""

from collections.abc import Sequence

from alembic import op

revision: str = "u5t3s61n8l4j"
down_revision: str | Sequence[str] | None = "t4s2r50m7k3i"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_engineering_executions_command_scope",
        "engineering_executions",
        ["company_id", "id", "command_id"],
    )
    op.drop_constraint(
        "fk_execution_compositions_execution",
        "engineering_execution_compositions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "engineering_execution_compositions_command_id_fkey",
        "engineering_execution_compositions",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_execution_compositions_execution_command",
        "engineering_execution_compositions",
        "engineering_executions",
        ["company_id", "execution_id", "command_id"],
        ["company_id", "id", "command_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_execution_compositions_execution_command",
        "engineering_execution_compositions",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_execution_compositions_execution",
        "engineering_execution_compositions",
        "engineering_executions",
        ["company_id", "execution_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "engineering_execution_compositions_command_id_fkey",
        "engineering_execution_compositions",
        "engineering_commands",
        ["command_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "uq_engineering_executions_command_scope",
        "engineering_executions",
        type_="unique",
    )
