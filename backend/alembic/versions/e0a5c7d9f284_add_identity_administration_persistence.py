"""add identity administration persistence

Revision ID: e0a5c7d9f284
Revises: d9f4b6c8e173
Create Date: 2026-07-20
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e0a5c7d9f284"
down_revision: str | None = "d9f4b6c8e173"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_credentials",
        sa.Column(
            "password_change_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "user_credentials",
        sa.Column("password_change_required_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "user_credentials",
        sa.Column("password_change_required_reason_code", sa.String(length=40)),
    )
    op.add_column(
        "user_credentials",
        sa.Column(
            "password_change_required_by_user_id",
            postgresql.UUID(as_uuid=True),
        ),
    )
    op.add_column(
        "user_credentials",
        sa.Column(
            "password_change_required_company_id",
            postgresql.UUID(as_uuid=True),
        ),
    )
    op.add_column(
        "user_credentials",
        sa.Column("password_change_required_cleared_at", sa.DateTime(timezone=True)),
    )
    op.alter_column("user_credentials", "password_change_required", server_default=None)
    op.create_foreign_key(
        "fk_user_credentials_reset_actor_users",
        "user_credentials",
        "users",
        ["password_change_required_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_user_credentials_reset_company_companies",
        "user_credentials",
        "companies",
        ["password_change_required_company_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_user_credentials_password_change_required_state",
        "user_credentials",
        "(password_change_required = true "
        "AND password_change_required_at IS NOT NULL "
        "AND password_change_required_reason_code IS NOT NULL "
        "AND password_change_required_by_user_id IS NOT NULL "
        "AND password_change_required_cleared_at IS NULL) OR "
        "(password_change_required = false "
        "AND ((password_change_required_at IS NULL "
        "AND password_change_required_reason_code IS NULL "
        "AND password_change_required_by_user_id IS NULL "
        "AND password_change_required_company_id IS NULL "
        "AND password_change_required_cleared_at IS NULL) OR "
        "(password_change_required_at IS NOT NULL "
        "AND password_change_required_reason_code IS NOT NULL "
        "AND password_change_required_by_user_id IS NOT NULL "
        "AND password_change_required_cleared_at IS NOT NULL)))",
    )
    op.create_check_constraint(
        "ck_user_credentials_password_change_required_reason",
        "user_credentials",
        "password_change_required_reason_code IS NULL OR "
        "password_change_required_reason_code IN "
        "('administrator_required', 'security_incident', "
        "'credential_recovery', 'policy_compliance')",
    )
    op.create_check_constraint(
        "ck_user_credentials_password_change_required_timestamps",
        "user_credentials",
        "password_change_required_cleared_at IS NULL OR "
        "password_change_required_cleared_at >= password_change_required_at",
    )
    op.create_index(
        "ix_user_credentials_password_change_required",
        "user_credentials",
        ["user_id"],
        postgresql_where=sa.text("password_change_required = true"),
    )

    op.create_table(
        "pending_email_changes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("proposed_normalized_email", sa.String(length=320), nullable=False),
        sa.Column("proposed_display_email", sa.String(length=320)),
        sa.Column("verification_token_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reason_code", sa.String(length=40), nullable=False),
        sa.Column("initiated_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("initiating_company_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.Column("expired_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "length(btrim(proposed_normalized_email)) > 0 "
            "AND proposed_normalized_email = lower(btrim(proposed_normalized_email))",
            name="ck_pending_email_changes_normalized_email",
        ),
        sa.CheckConstraint(
            "proposed_display_email IS NULL "
            "OR length(btrim(proposed_display_email)) > 0",
            name="ck_pending_email_changes_display_email_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(verification_token_hash)) > 0",
            name="ck_pending_email_changes_token_hash_not_blank",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'revoked', 'superseded', 'expired')",
            name="ck_pending_email_changes_status",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_pending_email_changes_expiration",
        ),
        sa.CheckConstraint(
            "reason_code IN "
            "('self_service', 'company_administration', 'platform_administration')",
            name="ck_pending_email_changes_reason_code",
        ),
        sa.CheckConstraint(
            "reason_code <> 'company_administration' "
            "OR initiating_company_id IS NOT NULL",
            name="ck_pending_email_changes_company_admin_origin",
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND confirmed_at IS NULL AND revoked_at IS NULL "
            "AND superseded_at IS NULL AND expired_at IS NULL) OR "
            "(status = 'confirmed' AND confirmed_at IS NOT NULL "
            "AND revoked_at IS NULL AND superseded_at IS NULL AND expired_at IS NULL) OR "
            "(status = 'revoked' AND revoked_at IS NOT NULL "
            "AND confirmed_at IS NULL AND superseded_at IS NULL AND expired_at IS NULL) OR "
            "(status = 'superseded' AND superseded_at IS NOT NULL "
            "AND confirmed_at IS NULL AND revoked_at IS NULL AND expired_at IS NULL) OR "
            "(status = 'expired' AND expired_at IS NOT NULL "
            "AND confirmed_at IS NULL AND revoked_at IS NULL AND superseded_at IS NULL)",
            name="ck_pending_email_changes_lifecycle",
        ),
        sa.CheckConstraint(
            "confirmed_at IS NULL OR confirmed_at >= created_at",
            name="ck_pending_email_changes_confirmed_timestamp",
        ),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name="ck_pending_email_changes_revoked_timestamp",
        ),
        sa.CheckConstraint(
            "superseded_at IS NULL OR superseded_at >= created_at",
            name="ck_pending_email_changes_superseded_timestamp",
        ),
        sa.CheckConstraint(
            "expired_at IS NULL OR expired_at >= created_at",
            name="ck_pending_email_changes_expired_timestamp",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_pending_email_changes_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["initiated_by_user_id"],
            ["users.id"],
            name="fk_pending_email_changes_initiated_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["initiating_company_id"],
            ["companies.id"],
            name="fk_pending_email_changes_initiating_company_id_companies",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pending_email_changes"),
    )
    op.create_index(
        "uq_pending_email_changes_active_user",
        "pending_email_changes",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "uq_pending_email_changes_active_email",
        "pending_email_changes",
        ["proposed_normalized_email"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "ix_pending_email_changes_token_hash",
        "pending_email_changes",
        ["verification_token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_pending_email_changes_user_id_status",
        "pending_email_changes",
        ["user_id", "status"],
    )
    op.create_index(
        "ix_pending_email_changes_status_expires_at",
        "pending_email_changes",
        ["status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pending_email_changes_status_expires_at",
        table_name="pending_email_changes",
    )
    op.drop_index(
        "ix_pending_email_changes_user_id_status",
        table_name="pending_email_changes",
    )
    op.drop_index(
        "ix_pending_email_changes_token_hash",
        table_name="pending_email_changes",
    )
    op.drop_index(
        "uq_pending_email_changes_active_email",
        table_name="pending_email_changes",
    )
    op.drop_index(
        "uq_pending_email_changes_active_user",
        table_name="pending_email_changes",
    )
    op.drop_table("pending_email_changes")

    op.drop_index(
        "ix_user_credentials_password_change_required",
        table_name="user_credentials",
    )
    op.drop_constraint(
        "ck_user_credentials_password_change_required_timestamps",
        "user_credentials",
        type_="check",
    )
    op.drop_constraint(
        "ck_user_credentials_password_change_required_reason",
        "user_credentials",
        type_="check",
    )
    op.drop_constraint(
        "ck_user_credentials_password_change_required_state",
        "user_credentials",
        type_="check",
    )
    op.drop_constraint(
        "fk_user_credentials_reset_company_companies",
        "user_credentials",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_user_credentials_reset_actor_users",
        "user_credentials",
        type_="foreignkey",
    )
    op.drop_column("user_credentials", "password_change_required_cleared_at")
    op.drop_column("user_credentials", "password_change_required_company_id")
    op.drop_column("user_credentials", "password_change_required_by_user_id")
    op.drop_column("user_credentials", "password_change_required_reason_code")
    op.drop_column("user_credentials", "password_change_required_at")
    op.drop_column("user_credentials", "password_change_required")
