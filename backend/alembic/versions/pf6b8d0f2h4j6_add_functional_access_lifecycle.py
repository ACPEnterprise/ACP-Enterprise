"""add functional access lifecycle to canonical role grants

Revision ID: pf6b8d0f2h4j6
Revises: pe5a7c9e1g3i5
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "pf6b8d0f2h4j6"
down_revision: str | Sequence[str] | None = "pe5a7c9e1g3i5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("membership_roles", sa.Column("functional_area", sa.String(50)))
    op.add_column("membership_roles", sa.Column("access_level", sa.String(50)))
    op.add_column(
        "membership_roles",
        sa.Column("effective_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "membership_roles", sa.Column("expires_at", sa.DateTime(timezone=True))
    )
    op.add_column("membership_roles", sa.Column("grant_reason", sa.Text()))
    op.add_column(
        "membership_roles",
        sa.Column("revoked_by_user_id", postgresql.UUID(as_uuid=True)),
    )
    op.add_column("membership_roles", sa.Column("revocation_reason", sa.Text()))
    op.create_check_constraint(
        "ck_membership_roles_expiration_after_effective",
        "membership_roles",
        "expires_at IS NULL OR effective_at IS NULL OR expires_at > effective_at",
    )
    op.create_check_constraint(
        "ck_membership_roles_functional_access_pair",
        "membership_roles",
        "(functional_area IS NULL) = (access_level IS NULL)",
    )
    op.create_foreign_key(
        "fk_membership_roles_revoked_by_user_id_users",
        "membership_roles",
        "users",
        ["revoked_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_membership_roles_functional_effective",
        "membership_roles",
        [
            "company_id",
            "membership_id",
            "functional_area",
            "effective_at",
            "expires_at",
        ],
    )
    # Classify existing canonical grants without changing their authority. This
    # makes established Employees visible in the functional-access UI while
    # preserving the original grant, actor, and assignment timestamp.
    op.execute(
        sa.text(
            """
            UPDATE membership_roles AS membership_role
            SET functional_area = mapping.functional_area,
                access_level = mapping.access_level,
                effective_at = membership_role.assigned_at,
                grant_reason = 'Reconciled existing canonical role grant'
            FROM roles AS role
            JOIN (
                VALUES
                    ('TECHNICIAN', 'FIELD_OPERATIONS', 'TECHNICIAN'),
                    ('CSR', 'CUSTOMER_SERVICE', 'CSR'),
                    ('DISPATCHER', 'DISPATCH', 'DISPATCHER'),
                    ('AUDITOR', 'REPORTING_ECONOMICS', 'READ')
            ) AS mapping(role_code, functional_area, access_level)
              ON mapping.role_code = role.code
            WHERE membership_role.role_id = role.id
              AND membership_role.company_id = role.company_id
              AND membership_role.functional_area IS NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_index(
        "ix_membership_roles_functional_effective", table_name="membership_roles"
    )
    op.drop_constraint(
        "fk_membership_roles_revoked_by_user_id_users",
        "membership_roles",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_membership_roles_functional_access_pair",
        "membership_roles",
        type_="check",
    )
    op.drop_constraint(
        "ck_membership_roles_expiration_after_effective",
        "membership_roles",
        type_="check",
    )
    for column in (
        "revocation_reason",
        "revoked_by_user_id",
        "grant_reason",
        "expires_at",
        "effective_at",
        "access_level",
        "functional_area",
    ):
        op.drop_column("membership_roles", column)
