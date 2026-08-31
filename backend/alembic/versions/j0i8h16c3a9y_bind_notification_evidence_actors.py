"""Bind notification delivery evidence actors to user and Company authority.

Revision ID: j0i8h16c3a9y
Revises: i9h7g05b2z8x
"""

from collections.abc import Sequence

from alembic import op

revision: str = "j0i8h16c3a9y"
down_revision: str | Sequence[str] | None = "i9h7g05b2z8x"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_notification_delivery_evidence_actor_user",
        "notification_delivery_evidence",
        "users",
        ["actor_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_notification_delivery_evidence_actor_membership",
        "notification_delivery_evidence",
        "memberships",
        ["actor_user_id", "company_id"],
        ["user_id", "company_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_notification_delivery_evidence_actor_membership",
        "notification_delivery_evidence",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_notification_delivery_evidence_actor_user",
        "notification_delivery_evidence",
        type_="foreignkey",
    )
