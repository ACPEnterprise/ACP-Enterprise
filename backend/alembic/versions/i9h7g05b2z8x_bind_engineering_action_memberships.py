"""Bind Engineering Control action actors to Company membership.

Revision ID: i9h7g05b2z8x
Revises: h8g6f94a1y7w
"""

from collections.abc import Sequence

from alembic import op

revision: str = "i9h7g05b2z8x"
down_revision: str | Sequence[str] | None = "h8g6f94a1y7w"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for name, table, column in (
        (
            "fk_engineering_milestone_events_actor_membership",
            "engineering_milestone_events",
            "actor_user_id",
        ),
        (
            "fk_external_adoptions_adopter_membership",
            "engineering_external_milestone_adoptions",
            "adopted_by_user_id",
        ),
        (
            "fk_external_adoptions_approver_membership",
            "engineering_external_milestone_adoptions",
            "approval_by_user_id",
        ),
        (
            "fk_external_evidence_submitter_membership",
            "engineering_external_milestone_evidence",
            "submitted_by_user_id",
        ),
        (
            "fk_mission_notifications_ack_membership",
            "engineering_mission_notifications",
            "acknowledged_by_user_id",
        ),
    ):
        op.create_foreign_key(
            name,
            table,
            "memberships",
            [column, "company_id"],
            ["user_id", "company_id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    for name, table in (
        (
            "fk_mission_notifications_ack_membership",
            "engineering_mission_notifications",
        ),
        (
            "fk_external_evidence_submitter_membership",
            "engineering_external_milestone_evidence",
        ),
        (
            "fk_external_adoptions_approver_membership",
            "engineering_external_milestone_adoptions",
        ),
        (
            "fk_external_adoptions_adopter_membership",
            "engineering_external_milestone_adoptions",
        ),
        (
            "fk_engineering_milestone_events_actor_membership",
            "engineering_milestone_events",
        ),
    ):
        op.drop_constraint(name, table, type_="foreignkey")
