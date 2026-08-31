"""Bind execution nodes and provider transitions to tenant authority.

Revision ID: v6u4t72o9m5k
Revises: u5t3s61n8l4j
"""

from collections.abc import Sequence

from alembic import op

revision: str = "v6u4t72o9m5k"
down_revision: str | Sequence[str] | None = "u5t3s61n8l4j"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_execution_nodes_company_id",
        "engineering_execution_nodes",
        ["company_id", "id"],
    )
    op.drop_constraint(
        "engineering_execution_nodes_worker_id_fkey",
        "engineering_execution_nodes",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_execution_nodes_worker_company",
        "engineering_execution_nodes",
        "engineering_workers",
        ["company_id", "worker_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )

    for name in (
        "engineering_provider_execution_transitions_command_id_fkey",
        "engineering_provider_execution_transitions_execution_id_fkey",
        "engineering_provider_execution_transitions_node_id_fkey",
        "engineering_provider_execution_transitions_lease_id_fkey",
    ):
        op.drop_constraint(
            name, "engineering_provider_execution_transitions", type_="foreignkey"
        )
    op.create_foreign_key(
        "fk_provider_transitions_execution_command",
        "engineering_provider_execution_transitions",
        "engineering_executions",
        ["company_id", "execution_id", "command_id"],
        ["company_id", "id", "command_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_provider_transitions_node_company",
        "engineering_provider_execution_transitions",
        "engineering_execution_nodes",
        ["company_id", "node_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_provider_transitions_lease_company",
        "engineering_provider_execution_transitions",
        "engineering_worker_leases",
        ["company_id", "lease_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    for name in (
        "fk_provider_transitions_execution_command",
        "fk_provider_transitions_node_company",
        "fk_provider_transitions_lease_company",
    ):
        op.drop_constraint(
            name, "engineering_provider_execution_transitions", type_="foreignkey"
        )
    for name, column, parent in (
        (
            "engineering_provider_execution_transitions_command_id_fkey",
            "command_id",
            "engineering_commands",
        ),
        (
            "engineering_provider_execution_transitions_execution_id_fkey",
            "execution_id",
            "engineering_executions",
        ),
        (
            "engineering_provider_execution_transitions_node_id_fkey",
            "node_id",
            "engineering_execution_nodes",
        ),
        (
            "engineering_provider_execution_transitions_lease_id_fkey",
            "lease_id",
            "engineering_worker_leases",
        ),
    ):
        op.create_foreign_key(
            name,
            "engineering_provider_execution_transitions",
            parent,
            [column],
            ["id"],
            ondelete="RESTRICT",
        )

    op.drop_constraint(
        "fk_execution_nodes_worker_company",
        "engineering_execution_nodes",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "engineering_execution_nodes_worker_id_fkey",
        "engineering_execution_nodes",
        "engineering_workers",
        ["worker_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "uq_execution_nodes_company_id",
        "engineering_execution_nodes",
        type_="unique",
    )
