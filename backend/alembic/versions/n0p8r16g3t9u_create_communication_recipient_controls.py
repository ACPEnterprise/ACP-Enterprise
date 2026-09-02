"""create communication recipient controls

Revision ID: n0p8r16g3t9u
Revises: m9n7q05f2s8t
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "n0p8r16g3t9u"
down_revision: str | None = "m9n7q05f2s8t"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "communication_recipient_controls",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("destination_digest", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("provider_event_key", sa.String(length=200), nullable=True),
        sa.Column("source_evidence_digest", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "channel IN ('email', 'sms')", name="ck_recipient_control_channel"
        ),
        sa.CheckConstraint(
            "scope IN ('all', 'marketing_outreach', 'operational', 'transactional')",
            name="ck_recipient_control_scope",
        ),
        sa.CheckConstraint(
            "source IN ('customer_no_contact', 'marketing_opt_out', 'sms_stop', "
            "'email_unsubscribe', 'invalid_recipient', 'hard_bounce', "
            "'provider_suppression', 'company_administrator')",
            name="ck_recipient_control_source",
        ),
        sa.CheckConstraint(
            "length(destination_digest) = 64",
            name="ck_recipient_control_destination_digest",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_recipient_control_lookup",
        "communication_recipient_controls",
        [
            "company_id",
            "channel",
            "destination_digest",
            "scope",
            "source",
            "occurred_at",
        ],
    )
    op.create_index(
        "uq_recipient_control_provider_event",
        "communication_recipient_controls",
        ["company_id", "provider_event_key"],
        unique=True,
        postgresql_where=sa.text("provider_event_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_recipient_control_provider_event",
        table_name="communication_recipient_controls",
    )
    op.drop_index(
        "ix_recipient_control_lookup",
        table_name="communication_recipient_controls",
    )
    op.drop_table("communication_recipient_controls")
