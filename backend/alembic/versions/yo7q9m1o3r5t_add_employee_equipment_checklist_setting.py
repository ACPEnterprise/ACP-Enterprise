"""Add governed Employee equipment checklist responsibility setting."""

import sqlalchemy as sa

from alembic import op


revision = "yo7q9m1o3r5t"
down_revision = "xn6p8r0t2v4x"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column(
            "equipment_checklist_requirement",
            sa.String(length=32),
            nullable=False,
            server_default="not_required",
        ),
    )
    op.create_check_constraint(
        "ck_employees_equipment_checklist_requirement",
        "employees",
        "equipment_checklist_requirement IN ('not_required', 'required_at_clock_in')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_employees_equipment_checklist_requirement",
        "employees",
        type_="check",
    )
    op.drop_column("employees", "equipment_checklist_requirement")
