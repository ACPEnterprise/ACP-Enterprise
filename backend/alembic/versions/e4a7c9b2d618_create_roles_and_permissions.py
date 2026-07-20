"""create roles and permissions

Revision ID: e4a7c9b2d618
Revises: d2e6f8a1b405
Create Date: 2026-07-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e4a7c9b2d618"
down_revision: Union[str, Sequence[str], None] = "d2e6f8a1b405"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "permissions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("resource", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(btrim(code)) > 0 AND code = upper(btrim(code))",
            name="ck_permissions_code_normalized",
        ),
        sa.CheckConstraint(
            "length(btrim(name)) > 0",
            name="ck_permissions_name_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(resource)) > 0",
            name="ck_permissions_resource_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(action)) > 0",
            name="ck_permissions_action_not_blank",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'retired')",
            name="ck_permissions_status",
        ),
        sa.CheckConstraint(
            "(status = 'retired') = (retired_at IS NOT NULL)",
            name="ck_permissions_retired_timestamp",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_permissions"),
        sa.UniqueConstraint("code", name="uq_permissions_code"),
    )
    op.create_index(
        "ix_permissions_resource_action",
        "permissions",
        ["resource", "action"],
    )

    op.create_table(
        "roles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        sa.Column("updated_by_user_id", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "length(btrim(code)) > 0 AND code = upper(btrim(code))",
            name="ck_roles_code_normalized",
        ),
        sa.CheckConstraint(
            "length(btrim(name)) > 0",
            name="ck_roles_name_not_blank",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'inactive', 'archived')",
            name="ck_roles_status",
        ),
        sa.CheckConstraint(
            "(status = 'archived') = (archived_at IS NOT NULL)",
            name="ck_roles_archived_timestamp",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_roles_company_id_companies",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_roles_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name="fk_roles_updated_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_roles"),
        sa.UniqueConstraint(
            "company_id",
            "id",
            name="uq_roles_company_id_id",
        ),
    )
    op.create_index(
        "ix_roles_company_id_status",
        "roles",
        ["company_id", "status"],
    )
    op.create_index(
        "uq_roles_active_company_code",
        "roles",
        ["company_id", "code"],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
    )

    op.create_table(
        "role_permissions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("role_id", sa.UUID(), nullable=False),
        sa.Column("permission_id", sa.UUID(), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_by_user_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["assigned_by_user_id"],
            ["users.id"],
            name="fk_role_permissions_assigned_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name="fk_role_permissions_permission_id_permissions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name="fk_role_permissions_role_id_roles",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_role_permissions"),
        sa.UniqueConstraint(
            "role_id",
            "permission_id",
            name="uq_role_permissions_role_id_permission_id",
        ),
    )
    op.create_index(
        "ix_role_permissions_permission_id",
        "role_permissions",
        ["permission_id"],
    )
    op.create_index(
        "ix_role_permissions_role_id",
        "role_permissions",
        ["role_id"],
    )

    op.create_table(
        "membership_roles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("membership_id", sa.UUID(), nullable=False),
        sa.Column("role_id", sa.UUID(), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_by_user_id", sa.UUID(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= assigned_at",
            name="ck_membership_roles_revocation_after_assignment",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by_user_id"],
            ["users.id"],
            name="fk_membership_roles_assigned_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "membership_id"],
            ["memberships.company_id", "memberships.id"],
            name="fk_membership_roles_company_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "role_id"],
            ["roles.company_id", "roles.id"],
            name="fk_membership_roles_company_role",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_membership_roles"),
    )
    op.create_index(
        "ix_membership_roles_membership_id",
        "membership_roles",
        ["membership_id"],
    )
    op.create_index(
        "ix_membership_roles_role_id",
        "membership_roles",
        ["role_id"],
    )
    op.create_index(
        "uq_membership_roles_active_membership_role",
        "membership_roles",
        ["membership_id", "role_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_membership_roles_active_membership_role",
        table_name="membership_roles",
    )
    op.drop_index("ix_membership_roles_role_id", table_name="membership_roles")
    op.drop_index(
        "ix_membership_roles_membership_id",
        table_name="membership_roles",
    )
    op.drop_table("membership_roles")
    op.drop_index("ix_role_permissions_role_id", table_name="role_permissions")
    op.drop_index(
        "ix_role_permissions_permission_id",
        table_name="role_permissions",
    )
    op.drop_table("role_permissions")
    op.drop_index("uq_roles_active_company_code", table_name="roles")
    op.drop_index("ix_roles_company_id_status", table_name="roles")
    op.drop_table("roles")
    op.drop_index("ix_permissions_resource_action", table_name="permissions")
    op.drop_table("permissions")
