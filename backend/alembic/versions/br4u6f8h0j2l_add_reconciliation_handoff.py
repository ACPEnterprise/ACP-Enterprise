"""add authenticated bank reconciliation handoff lifecycle

Revision ID: br4u6f8h0j2l
Revises: bn3t5e7q9d1w
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "br4u6f8h0j2l"
down_revision: str | Sequence[str] | None = "bn3t5e7q9d1w"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_bank_reconciliation_status",
        "accounting_bank_reconciliations",
        type_="check",
    )
    op.execute(
        "UPDATE accounting_bank_reconciliations "
        "SET status = CASE "
        "WHEN status = 'ready_to_close' THEN 'ready_to_submit' "
        "WHEN status = 'review_required' THEN 'draft' ELSE status END"
    )
    op.add_column(
        "accounting_bank_reconciliations",
        sa.Column("preparer_membership_id", postgresql.UUID(as_uuid=True)),
    )
    op.add_column(
        "accounting_bank_reconciliations",
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "accounting_bank_reconciliations",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.execute(
        "UPDATE accounting_bank_reconciliations "
        "SET submitted_at = closed_at WHERE status = 'closed'"
    )
    op.create_foreign_key(
        "fk_bank_reconciliation_preparer_membership",
        "accounting_bank_reconciliations",
        "memberships",
        ["preparer_membership_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_bank_reconciliation_status",
        "accounting_bank_reconciliations",
        "status IN ('draft','ready_to_submit','submitted_for_review','closed')",
    )
    op.create_check_constraint(
        "ck_bank_reconciliation_version",
        "accounting_bank_reconciliations",
        "version >= 1",
    )
    op.create_check_constraint(
        "ck_bank_reconciliation_submission_integrity",
        "accounting_bank_reconciliations",
        "status NOT IN ('submitted_for_review','closed') OR submitted_at IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_bank_reconciliation_submission_integrity",
        "accounting_bank_reconciliations",
        type_="check",
    )
    op.drop_constraint(
        "ck_bank_reconciliation_version",
        "accounting_bank_reconciliations",
        type_="check",
    )
    op.drop_constraint(
        "ck_bank_reconciliation_status",
        "accounting_bank_reconciliations",
        type_="check",
    )
    op.execute(
        "UPDATE accounting_bank_reconciliations "
        "SET status = CASE "
        "WHEN status = 'ready_to_submit' THEN 'ready_to_close' "
        "WHEN status = 'submitted_for_review' THEN 'ready_to_close' ELSE status END"
    )
    op.create_check_constraint(
        "ck_bank_reconciliation_status",
        "accounting_bank_reconciliations",
        "status IN ('draft','review_required','ready_to_close','closed')",
    )
    op.drop_constraint(
        "fk_bank_reconciliation_preparer_membership",
        "accounting_bank_reconciliations",
        type_="foreignkey",
    )
    op.drop_column("accounting_bank_reconciliations", "version")
    op.drop_column("accounting_bank_reconciliations", "submitted_at")
    op.drop_column("accounting_bank_reconciliations", "preparer_membership_id")
