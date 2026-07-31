"""create worker transport persistence

Revision ID: c3e5a7b9d124
Revises: b2d4f6a8c013
Create Date: 2026-07-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c3e5a7b9d124"
down_revision: str | None = "b2d4f6a8c013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "engineering_worker_transport_challenges",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("challenge_digest", sa.String(length=64), nullable=False),
        sa.Column("key_version", sa.String(length=100), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(challenge_digest) = 64",
            name="ck_worker_transport_challenges_digest",
        ),
        sa.CheckConstraint(
            "expires_at > issued_at",
            name="ck_worker_transport_challenges_expiration",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "worker_id"],
            ["engineering_workers.company_id", "engineering_workers.id"],
            name="fk_worker_transport_challenges_worker",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_worker_transport_challenges_company_id"
        ),
    )
    op.create_index(
        "ix_worker_transport_challenges_worker_expiration",
        "engineering_worker_transport_challenges",
        ["company_id", "worker_id", "expires_at"],
    )
    op.create_table(
        "engineering_worker_transport_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_identifier", sa.String(length=100), nullable=False),
        sa.Column(
            "authentication_subject_digest", sa.String(length=64), nullable=False
        ),
        sa.Column("capabilities", postgresql.JSONB(), nullable=False),
        sa.Column("key_version", sa.String(length=100), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("established_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_sequence", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "state IN ('active','expired','revoked')",
            name="ck_worker_transport_sessions_state",
        ),
        sa.CheckConstraint(
            "expires_at > established_at",
            name="ck_worker_transport_sessions_expiration",
        ),
        sa.CheckConstraint(
            "next_sequence >= 1", name="ck_worker_transport_sessions_sequence"
        ),
        sa.CheckConstraint("version >= 1", name="ck_worker_transport_sessions_version"),
        sa.CheckConstraint(
            "length(authentication_subject_digest) = 64",
            name="ck_worker_transport_sessions_subject_digest",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "worker_id"],
            ["engineering_workers.company_id", "engineering_workers.id"],
            name="fk_worker_transport_sessions_worker",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_worker_transport_sessions_company_id"
        ),
    )
    op.create_index(
        "ix_worker_transport_sessions_worker_state",
        "engineering_worker_transport_sessions",
        ["company_id", "worker_id", "state", "expires_at"],
    )
    op.create_table(
        "engineering_worker_transport_receipts",
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("envelope_digest", sa.String(length=64), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome_reference", sa.String(length=255), nullable=False),
        sa.CheckConstraint(
            "sequence_number >= 1", name="ck_worker_transport_receipts_sequence"
        ),
        sa.CheckConstraint(
            "length(envelope_digest) = 64",
            name="ck_worker_transport_receipts_digest",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "session_id"],
            [
                "engineering_worker_transport_sessions.company_id",
                "engineering_worker_transport_sessions.id",
            ],
            name="fk_worker_transport_receipts_session",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "worker_id"],
            ["engineering_workers.company_id", "engineering_workers.id"],
            name="fk_worker_transport_receipts_worker",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("message_id"),
        sa.UniqueConstraint(
            "company_id",
            "session_id",
            "sequence_number",
            name="uq_worker_transport_receipts_session_sequence",
        ),
    )
    op.create_index(
        "ix_worker_transport_receipts_session_accepted",
        "engineering_worker_transport_receipts",
        ["company_id", "session_id", "accepted_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_worker_transport_receipts_session_accepted",
        table_name="engineering_worker_transport_receipts",
    )
    op.drop_table("engineering_worker_transport_receipts")
    op.drop_index(
        "ix_worker_transport_sessions_worker_state",
        table_name="engineering_worker_transport_sessions",
    )
    op.drop_table("engineering_worker_transport_sessions")
    op.drop_index(
        "ix_worker_transport_challenges_worker_expiration",
        table_name="engineering_worker_transport_challenges",
    )
    op.drop_table("engineering_worker_transport_challenges")
