"""Create append-only manual paper-check evidence for Issue #449."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "pb449d0e2f3a1"
down_revision: Union[str, Sequence[str], None] = "pa449c0d1e2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payroll_paper_check_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("check_number", sa.String(80), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("lifecycle", sa.String(16), nullable=False),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("replay_identity", sa.String(180), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("void_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id", "run_id"], ["payroll_runs.company_id", "payroll_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id", "employee_id"], ["employees.company_id", "employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supersedes_id"], ["payroll_paper_check_evidence.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "replay_identity", name="uq_payroll_paper_check_replay"),
        sa.UniqueConstraint("company_id", "check_number", name="uq_payroll_paper_check_number"),
        sa.CheckConstraint("lifecycle IN ('issued','voided','reissued')", name="ck_payroll_paper_check_lifecycle"),
    )


def downgrade() -> None:
    op.drop_table("payroll_paper_check_evidence")
