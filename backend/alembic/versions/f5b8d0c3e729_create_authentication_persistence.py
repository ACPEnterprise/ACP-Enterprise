"""create authentication persistence

Revision ID: f5b8d0c3e729
Revises: e4a7c9b2d618
Create Date: 2026-07-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f5b8d0c3e729"
down_revision: Union[str, Sequence[str], None] = "e4a7c9b2d618"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "authentication_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.String(length=200), nullable=True),
        sa.Column("revoked_by_user_id", sa.UUID(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("device_label", sa.String(length=200), nullable=True),
        sa.Column("authentication_method", sa.String(length=50), nullable=False),
        sa.Column("credential_version", sa.Integer(), nullable=False),
        sa.Column("authorization_version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'revoked', 'expired', 'compromised')",
            name="ck_authentication_sessions_status",
        ),
        sa.CheckConstraint(
            "absolute_expires_at > created_at",
            name="ck_authentication_sessions_absolute_expiration",
        ),
        sa.CheckConstraint(
            "idle_expires_at IS NULL OR "
            "(idle_expires_at > created_at "
            "AND idle_expires_at <= absolute_expires_at)",
            name="ck_authentication_sessions_idle_expiration",
        ),
        sa.CheckConstraint(
            "last_seen_at >= created_at",
            name="ck_authentication_sessions_last_seen",
        ),
        sa.CheckConstraint(
            "(status IN ('revoked', 'compromised')) = (revoked_at IS NOT NULL)",
            name="ck_authentication_sessions_revocation_status",
        ),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name="ck_authentication_sessions_revocation_timestamp",
        ),
        sa.CheckConstraint(
            "length(btrim(authentication_method)) > 0",
            name="ck_authentication_sessions_method_not_blank",
        ),
        sa.CheckConstraint(
            "credential_version >= 1",
            name="ck_authentication_sessions_credential_version",
        ),
        sa.CheckConstraint(
            "authorization_version >= 1",
            name="ck_authentication_sessions_authorization_version",
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by_user_id"],
            ["users.id"],
            name="fk_authentication_sessions_revoked_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_authentication_sessions_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_authentication_sessions"),
    )
    op.create_index(
        "ix_authentication_sessions_absolute_expires_at",
        "authentication_sessions",
        ["absolute_expires_at"],
    )
    op.create_index(
        "ix_authentication_sessions_idle_expires_at",
        "authentication_sessions",
        ["idle_expires_at"],
    )
    op.create_index(
        "ix_authentication_sessions_user_id_status",
        "authentication_sessions",
        ["user_id", "status"],
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("family_id", sa.UUID(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_token_id", sa.UUID(), nullable=True),
        sa.Column("parent_token_id", sa.UUID(), nullable=True),
        sa.Column("revocation_reason", sa.String(length=200), nullable=True),
        sa.Column("reuse_detected_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(btrim(token_hash)) > 0",
            name="ck_refresh_tokens_hash_not_blank",
        ),
        sa.CheckConstraint(
            "sequence_number >= 0",
            name="ck_refresh_tokens_sequence_number",
        ),
        sa.CheckConstraint(
            "expires_at > issued_at",
            name="ck_refresh_tokens_expiration",
        ),
        sa.CheckConstraint(
            "used_at IS NULL OR used_at >= issued_at",
            name="ck_refresh_tokens_used_timestamp",
        ),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= issued_at",
            name="ck_refresh_tokens_revoked_timestamp",
        ),
        sa.CheckConstraint(
            "reuse_detected_at IS NULL OR "
            "(used_at IS NOT NULL AND reuse_detected_at >= used_at)",
            name="ck_refresh_tokens_reuse_timestamp",
        ),
        sa.CheckConstraint(
            "replaced_by_token_id IS NULL OR used_at IS NOT NULL",
            name="ck_refresh_tokens_replacement_requires_use",
        ),
        sa.CheckConstraint(
            "replaced_by_token_id IS NULL OR replaced_by_token_id <> id",
            name="ck_refresh_tokens_not_self_replaced",
        ),
        sa.CheckConstraint(
            "parent_token_id IS NULL OR parent_token_id <> id",
            name="ck_refresh_tokens_not_self_parent",
        ),
        sa.ForeignKeyConstraint(
            ["parent_token_id"],
            ["refresh_tokens.id"],
            name="fk_refresh_tokens_parent_token_id_refresh_tokens",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by_token_id"],
            ["refresh_tokens.id"],
            name="fk_refresh_tokens_replaced_by_token_id_refresh_tokens",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["authentication_sessions.id"],
            name="fk_refresh_tokens_session_id_authentication_sessions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_refresh_tokens"),
        sa.UniqueConstraint(
            "family_id",
            "sequence_number",
            name="uq_refresh_tokens_family_id_sequence_number",
        ),
        sa.UniqueConstraint(
            "token_hash",
            name="uq_refresh_tokens_token_hash",
        ),
    )
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])
    op.create_index(
        "ix_refresh_tokens_session_id_expires_at",
        "refresh_tokens",
        ["session_id", "expires_at"],
    )

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("request_ip_address", sa.String(length=45), nullable=True),
        sa.Column("request_user_agent", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "length(btrim(token_hash)) > 0",
            name="ck_password_reset_tokens_hash_not_blank",
        ),
        sa.CheckConstraint(
            "expires_at > issued_at",
            name="ck_password_reset_tokens_expiration",
        ),
        sa.CheckConstraint(
            "consumed_at IS NULL OR consumed_at >= issued_at",
            name="ck_password_reset_tokens_consumed_timestamp",
        ),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= issued_at",
            name="ck_password_reset_tokens_revoked_timestamp",
        ),
        sa.CheckConstraint(
            "NOT (consumed_at IS NOT NULL AND revoked_at IS NOT NULL)",
            name="ck_password_reset_tokens_terminal_state",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_password_reset_tokens_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_password_reset_tokens"),
        sa.UniqueConstraint(
            "token_hash",
            name="uq_password_reset_tokens_token_hash",
        ),
    )
    op.create_index(
        "ix_password_reset_tokens_user_id_expires_at",
        "password_reset_tokens",
        ["user_id", "expires_at"],
    )

    op.create_table(
        "email_verification_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("normalized_email", sa.String(length=320), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(btrim(normalized_email)) > 0 "
            "AND normalized_email = lower(btrim(normalized_email))",
            name="ck_email_verification_tokens_normalized_email",
        ),
        sa.CheckConstraint(
            "length(btrim(token_hash)) > 0",
            name="ck_email_verification_tokens_hash_not_blank",
        ),
        sa.CheckConstraint(
            "expires_at > issued_at",
            name="ck_email_verification_tokens_expiration",
        ),
        sa.CheckConstraint(
            "consumed_at IS NULL OR consumed_at >= issued_at",
            name="ck_email_verification_tokens_consumed_timestamp",
        ),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= issued_at",
            name="ck_email_verification_tokens_revoked_timestamp",
        ),
        sa.CheckConstraint(
            "NOT (consumed_at IS NOT NULL AND revoked_at IS NOT NULL)",
            name="ck_email_verification_tokens_terminal_state",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_email_verification_tokens_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_email_verification_tokens"),
        sa.UniqueConstraint(
            "token_hash",
            name="uq_email_verification_tokens_token_hash",
        ),
    )
    op.create_index(
        "ix_email_verification_tokens_user_id_expires_at",
        "email_verification_tokens",
        ["user_id", "expires_at"],
    )

    op.create_table(
        "authentication_security_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("normalized_attempted_email", sa.String(length=320), nullable=True),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("failure_reason", sa.String(length=200), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("session_id", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "event_type IN ('login_succeeded', 'login_failed', 'account_locked', "
            "'password_reset_requested', 'password_reset_completed', "
            "'refresh_token_reused', 'session_revoked', "
            "'email_verification_requested', 'email_verified')",
            name="ck_authentication_security_events_type",
        ),
        sa.CheckConstraint(
            "normalized_attempted_email IS NULL OR "
            "(length(btrim(normalized_attempted_email)) > 0 AND "
            "normalized_attempted_email = lower(btrim(normalized_attempted_email)))",
            name="ck_authentication_security_events_normalized_email",
        ),
        sa.CheckConstraint(
            "NOT success OR failure_reason IS NULL",
            name="ck_authentication_security_events_success_reason",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["authentication_sessions.id"],
            name="fk_auth_security_events_session_id_sessions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_authentication_security_events_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_authentication_security_events"),
    )
    op.create_index(
        "ix_authentication_security_events_occurred_at",
        "authentication_security_events",
        ["occurred_at"],
    )
    op.create_index(
        "ix_authentication_security_events_session_id",
        "authentication_security_events",
        ["session_id"],
    )
    op.create_index(
        "ix_authentication_security_events_user_id",
        "authentication_security_events",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_authentication_security_events_user_id",
        table_name="authentication_security_events",
    )
    op.drop_index(
        "ix_authentication_security_events_session_id",
        table_name="authentication_security_events",
    )
    op.drop_index(
        "ix_authentication_security_events_occurred_at",
        table_name="authentication_security_events",
    )
    op.drop_table("authentication_security_events")
    op.drop_index(
        "ix_email_verification_tokens_user_id_expires_at",
        table_name="email_verification_tokens",
    )
    op.drop_table("email_verification_tokens")
    op.drop_index(
        "ix_password_reset_tokens_user_id_expires_at",
        table_name="password_reset_tokens",
    )
    op.drop_table("password_reset_tokens")
    op.drop_index(
        "ix_refresh_tokens_session_id_expires_at",
        table_name="refresh_tokens",
    )
    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index(
        "ix_authentication_sessions_user_id_status",
        table_name="authentication_sessions",
    )
    op.drop_index(
        "ix_authentication_sessions_idle_expires_at",
        table_name="authentication_sessions",
    )
    op.drop_index(
        "ix_authentication_sessions_absolute_expires_at",
        table_name="authentication_sessions",
    )
    op.drop_table("authentication_sessions")
