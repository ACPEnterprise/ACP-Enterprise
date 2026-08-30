"""create commercial engagement authority

Revision ID: d2bb4a1e7c0d
Revises: c1aa390d6bfc
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d2bb4a1e7c0d"
down_revision: str | Sequence[str] | None = "c1aa390d6bfc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_commercial_policy_type", "commercial_policy_versions", type_="check")
    op.create_check_constraint(
        "ck_commercial_policy_type",
        "commercial_policy_versions",
        "policy_type IN ('discount','price_override','estimate_expiration','rounding','tax_readiness','document_template','delivery_readiness','follow_up_cadence')",
    )
    op.create_table(
        "estimate_presentation_authorities",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("estimate_id", sa.UUID(), nullable=False),
        sa.Column("revision_id", sa.UUID(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("estimate_version", sa.Integer(), nullable=False),
        sa.Column("artifact_digest", sa.String(64), nullable=False),
        sa.Column("recipient_reference", sa.String(320), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("token_digest", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("viewed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("channel IN ('protected_link','print','email_preparation','sms_preparation')", name="ck_estimate_presentations_channel"),
        sa.CheckConstraint("status IN ('prepared','viewed','revoked','superseded')", name="ck_estimate_presentations_status"),
        sa.CheckConstraint("revision_number >= 1", name="ck_estimate_presentations_revision"),
        sa.CheckConstraint("estimate_version >= 1", name="ck_estimate_presentations_estimate_version"),
        sa.CheckConstraint("artifact_digest ~ '^[0-9a-f]{64}$'", name="ck_estimate_presentations_artifact_digest"),
        sa.CheckConstraint("evidence_digest ~ '^[0-9a-f]{64}$'", name="ck_estimate_presentations_evidence_digest"),
        sa.ForeignKeyConstraint(["company_id", "branch_id"], ["branches.company_id", "branches.id"], name="fk_estimate_presentations_branch", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id", "estimate_id"], ["estimate_proposals.company_id", "estimate_proposals.id"], name="fk_estimate_presentations_estimate", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id", "revision_id"], ["estimate_revisions.company_id", "estimate_revisions.id"], name="fk_estimate_presentations_revision", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "token_digest", name="uq_estimate_presentations_token"),
        sa.UniqueConstraint("company_id", "idempotency_key", name="uq_estimate_presentations_command"),
    )
    op.create_index("ix_estimate_presentations_timeline", "estimate_presentation_authorities", ["company_id", "estimate_id", "created_at"])

    op.create_table(
        "estimate_follow_up_evidence",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("estimate_id", sa.UUID(), nullable=False),
        sa.Column("revision_id", sa.UUID(), nullable=False),
        sa.Column("assigned_user_id", sa.UUID(), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("disposition", sa.String(240)),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("state IN ('open','snoozed','completed','canceled')", name="ck_estimate_followups_state"),
        sa.CheckConstraint("sequence >= 1", name="ck_estimate_followups_sequence"),
        sa.CheckConstraint("evidence_digest ~ '^[0-9a-f]{64}$'", name="ck_estimate_followups_digest"),
        sa.ForeignKeyConstraint(["company_id", "branch_id"], ["branches.company_id", "branches.id"], name="fk_estimate_followups_branch", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id", "estimate_id"], ["estimate_proposals.company_id", "estimate_proposals.id"], name="fk_estimate_followups_estimate", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id", "revision_id"], ["estimate_revisions.company_id", "estimate_revisions.id"], name="fk_estimate_followups_revision", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "estimate_id", "sequence", name="uq_estimate_followups_sequence"),
        sa.UniqueConstraint("company_id", "idempotency_key", name="uq_estimate_followups_command"),
    )
    op.create_index("ix_estimate_followups_queue", "estimate_follow_up_evidence", ["company_id", "branch_id", "state", "due_at"])


def downgrade() -> None:
    op.drop_index("ix_estimate_followups_queue", table_name="estimate_follow_up_evidence")
    op.drop_table("estimate_follow_up_evidence")
    op.drop_index("ix_estimate_presentations_timeline", table_name="estimate_presentation_authorities")
    op.drop_table("estimate_presentation_authorities")
    op.drop_constraint("ck_commercial_policy_type", "commercial_policy_versions", type_="check")
    op.create_check_constraint(
        "ck_commercial_policy_type",
        "commercial_policy_versions",
        "policy_type IN ('discount','price_override','estimate_expiration','rounding','tax_readiness','document_template','delivery_readiness')",
    )
