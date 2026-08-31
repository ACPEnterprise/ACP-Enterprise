"""Bind notification outbox Branch routing to Company authority.

Revision ID: d4c2b50w7u3s
Revises: c3b1a49v6t2r
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d4c2b50w7u3s"
down_revision: str | Sequence[str] | None = "c3b1a49v6t2r"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_notification_outbox_branch_requires_company",
        "notification_outbox",
        "branch_id IS NULL OR company_id IS NOT NULL",
    )
    op.create_foreign_key(
        "fk_notification_outbox_branch_scope",
        "notification_outbox",
        "branches",
        ["company_id", "branch_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_notification_outbox_branch_scope",
        "notification_outbox",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_notification_outbox_branch_requires_company",
        "notification_outbox",
        type_="check",
    )
