"""create identity and employee tables

Revision ID: d2e6f8a1b405
Revises: c7b9e1d4a632
Create Date: 2026-07-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d2e6f8a1b405"
down_revision: Union[str, Sequence[str], None] = "c7b9e1d4a632"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_branches_company_id_id",
        "branches",
        ["company_id", "id"],
    )

    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("normalized_email", sa.String(length=320), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("authorization_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(btrim(normalized_email)) > 0 "
            "AND normalized_email = lower(btrim(normalized_email))",
            name="ck_users_normalized_email",
        ),
        sa.CheckConstraint(
            "length(btrim(first_name)) > 0",
            name="ck_users_first_name_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(last_name)) > 0",
            name="ck_users_last_name_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(display_name)) > 0",
            name="ck_users_display_name_not_blank",
        ),
        sa.CheckConstraint(
            "status IN ('invited', 'active', 'disabled', 'locked')",
            name="ck_users_status",
        ),
        sa.CheckConstraint(
            "authorization_version >= 1",
            name="ck_users_authorization_version",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint(
            "normalized_email",
            name="uq_users_normalized_email",
        ),
    )
    op.create_index("ix_users_archived_at", "users", ["archived_at"])

    op.create_table(
        "user_credentials",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "password_changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("failed_login_count", sa.Integer(), nullable=False),
        sa.Column(
            "last_failed_login_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("credential_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(btrim(password_hash)) > 0",
            name="ck_user_credentials_password_hash_not_blank",
        ),
        sa.CheckConstraint(
            "failed_login_count >= 0",
            name="ck_user_credentials_failed_login_count",
        ),
        sa.CheckConstraint(
            "credential_version >= 1",
            name="ck_user_credentials_credential_version",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_credentials_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_credentials"),
        sa.UniqueConstraint("user_id", name="uq_user_credentials_user_id"),
    )

    op.create_table(
        "memberships",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("default_branch_id", sa.UUID(), nullable=True),
        sa.Column("has_all_branch_access", sa.Boolean(), nullable=False),
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('invited', 'active', 'suspended', 'revoked', 'archived')",
            name="ck_memberships_status",
        ),
        sa.CheckConstraint(
            "accepted_at IS NULL OR invited_at IS NULL OR accepted_at >= invited_at",
            name="ck_memberships_acceptance_after_invitation",
        ),
        sa.CheckConstraint(
            "revoked_at IS NULL OR status IN ('revoked', 'archived')",
            name="ck_memberships_revoked_status",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "default_branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_memberships_company_default_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_memberships_company_id_companies",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by_user_id"],
            ["users.id"],
            name="fk_memberships_revoked_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_memberships_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_memberships"),
        sa.UniqueConstraint(
            "company_id",
            "id",
            name="uq_memberships_company_id_id",
        ),
        sa.UniqueConstraint(
            "user_id",
            "company_id",
            name="uq_memberships_user_id_company_id",
        ),
    )
    op.create_index(
        "ix_memberships_company_id_status",
        "memberships",
        ["company_id", "status"],
    )
    op.create_index(
        "ix_memberships_default_branch_id",
        "memberships",
        ["default_branch_id"],
    )
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])

    op.create_table(
        "membership_branch_access",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("membership_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_by_user_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["assigned_by_user_id"],
            ["users.id"],
            name="fk_membership_branch_access_assigned_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["branch_id"],
            ["branches.id"],
            name="fk_membership_branch_access_branch_id_branches",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["membership_id"],
            ["memberships.id"],
            name="fk_membership_branch_access_membership_id_memberships",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_membership_branch_access"),
        sa.UniqueConstraint(
            "membership_id",
            "branch_id",
            name="uq_membership_branch_access_membership_id_branch_id",
        ),
    )
    op.create_index(
        "ix_membership_branch_access_branch_id",
        "membership_branch_access",
        ["branch_id"],
    )
    op.create_index(
        "ix_membership_branch_access_membership_id",
        "membership_branch_access",
        ["membership_id"],
    )

    op.create_table(
        "employees",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("membership_id", sa.UUID(), nullable=True),
        sa.Column("home_branch_id", sa.UUID(), nullable=True),
        sa.Column("employee_number", sa.String(length=50), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("job_title", sa.String(length=150), nullable=True),
        sa.Column("employee_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("hire_date", sa.Date(), nullable=True),
        sa.Column("termination_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        sa.Column("updated_by_user_id", sa.UUID(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(btrim(employee_number)) > 0",
            name="ck_employees_employee_number_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(first_name)) > 0",
            name="ck_employees_first_name_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(last_name)) > 0",
            name="ck_employees_last_name_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(display_name)) > 0",
            name="ck_employees_display_name_not_blank",
        ),
        sa.CheckConstraint(
            "employee_type IN ('employee', 'contractor', 'vendor')",
            name="ck_employees_employee_type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'inactive', 'leave', 'terminated')",
            name="ck_employees_status",
        ),
        sa.CheckConstraint(
            "termination_date IS NULL OR hire_date IS NULL "
            "OR termination_date >= hire_date",
            name="ck_employees_termination_after_hire",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "home_branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_employees_company_home_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "membership_id"],
            ["memberships.company_id", "memberships.id"],
            name="fk_employees_company_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_employees_company_id_companies",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_employees_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name="fk_employees_updated_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_employees"),
        sa.UniqueConstraint(
            "membership_id",
            name="uq_employees_membership_id",
        ),
    )
    op.create_index("ix_employees_archived_at", "employees", ["archived_at"])
    op.create_index(
        "ix_employees_company_id_status",
        "employees",
        ["company_id", "status"],
    )
    op.create_index(
        "ix_employees_home_branch_id",
        "employees",
        ["home_branch_id"],
    )
    op.create_index(
        "uq_employees_active_company_employee_number",
        "employees",
        ["company_id", "employee_number"],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_employees_active_company_employee_number",
        table_name="employees",
    )
    op.drop_index("ix_employees_home_branch_id", table_name="employees")
    op.drop_index("ix_employees_company_id_status", table_name="employees")
    op.drop_index("ix_employees_archived_at", table_name="employees")
    op.drop_table("employees")
    op.drop_index(
        "ix_membership_branch_access_membership_id",
        table_name="membership_branch_access",
    )
    op.drop_index(
        "ix_membership_branch_access_branch_id",
        table_name="membership_branch_access",
    )
    op.drop_table("membership_branch_access")
    op.drop_index("ix_memberships_user_id", table_name="memberships")
    op.drop_index("ix_memberships_default_branch_id", table_name="memberships")
    op.drop_index("ix_memberships_company_id_status", table_name="memberships")
    op.drop_table("memberships")
    op.drop_table("user_credentials")
    op.drop_index("ix_users_archived_at", table_name="users")
    op.drop_table("users")
    op.drop_constraint(
        "uq_branches_company_id_id",
        "branches",
        type_="unique",
    )
