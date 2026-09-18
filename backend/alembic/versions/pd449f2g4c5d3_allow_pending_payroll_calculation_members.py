"""Allow assembled Payroll runs to bind Employees before first calculation."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "pd449f2g4c5d3"
down_revision: Union[str, Sequence[str], None] = "pc449e1f3b4c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_payroll_run_member_disposition", "payroll_run_members", type_="check")
    op.create_check_constraint("ck_payroll_run_member_disposition", "payroll_run_members", "disposition IN ('pending_calculation','ready','blocked','excluded','not_applicable')")
    op.drop_constraint("ck_payroll_payment_instruction_disposition", "payroll_payment_instructions", type_="check")
    op.create_check_constraint("ck_payroll_payment_instruction_disposition", "payroll_payment_instructions", "disposition IN ('ready','blocked','excluded','not_applicable')")


def downgrade() -> None:
    op.drop_constraint("ck_payroll_run_member_disposition", "payroll_run_members", type_="check")
    op.create_check_constraint("ck_payroll_run_member_disposition", "payroll_run_members", "disposition IN ('ready','blocked','excluded','not_applicable')")
