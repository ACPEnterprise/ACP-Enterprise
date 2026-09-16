"""Create explicit real Workforce roster bindings.

Revision ID: n4p6r8t0v2x4
Revises: m3n5p7r9t1v3
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "n4p6r8t0v2x4"
down_revision: str | Sequence[str] | None = "m3n5p7r9t1v3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "real_workforce_roster_bindings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("roster_key", sa.String(length=64), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "confirmed_by_user_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "roster_key ~ '^[a-z][a-z0-9-]{0,63}$'",
            name="ck_real_workforce_roster_binding_key",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "employee_id"],
            ["employees.company_id", "employees.id"],
            name="fk_real_workforce_roster_binding_employee",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "employee_id", name="uq_real_workforce_roster_binding_employee"
        ),
        sa.UniqueConstraint(
            "company_id", "roster_key", name="uq_real_workforce_roster_binding_key"
        ),
    )


def downgrade() -> None:
    op.drop_table("real_workforce_roster_bindings")
