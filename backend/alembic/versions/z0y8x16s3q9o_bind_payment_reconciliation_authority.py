"""Bind Payment reconciliation evidence to scoped authority.

Revision ID: z0y8x16s3q9o
Revises: y9x7w05r2p8n
"""

from collections.abc import Sequence

from alembic import op

revision: str = "z0y8x16s3q9o"
down_revision: str | Sequence[str] | None = "y9x7w05r2p8n"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_payment_reconciliation_exceptions_branch_scope",
        "payment_reconciliation_exceptions",
        "branches",
        ["company_id", "branch_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_payment_reconciliation_exceptions_opened_by_user",
        "payment_reconciliation_exceptions",
        "users",
        ["opened_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_payment_reconciliation_exceptions_resolved_by_user",
        "payment_reconciliation_exceptions",
        "users",
        ["resolved_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_payment_reconciliation_exceptions_status",
        "payment_reconciliation_exceptions",
        "status IN ('open','resolved')",
    )
    op.create_check_constraint(
        "ck_payment_reconciliation_exceptions_digest",
        "payment_reconciliation_exceptions",
        "length(evidence_digest) = 64",
    )
    op.create_check_constraint(
        "ck_payment_reconciliation_exceptions_resolution",
        "payment_reconciliation_exceptions",
        "(status = 'open' AND resolved_by_user_id IS NULL AND resolved_at IS NULL) OR "
        "(status = 'resolved' AND resolved_by_user_id IS NOT NULL AND resolved_at IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_payment_reconciliation_exceptions_resolution",
        "payment_reconciliation_exceptions",
        type_="check",
    )
    op.drop_constraint(
        "ck_payment_reconciliation_exceptions_digest",
        "payment_reconciliation_exceptions",
        type_="check",
    )
    op.drop_constraint(
        "ck_payment_reconciliation_exceptions_status",
        "payment_reconciliation_exceptions",
        type_="check",
    )
    op.drop_constraint(
        "fk_payment_reconciliation_exceptions_resolved_by_user",
        "payment_reconciliation_exceptions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_payment_reconciliation_exceptions_opened_by_user",
        "payment_reconciliation_exceptions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_payment_reconciliation_exceptions_branch_scope",
        "payment_reconciliation_exceptions",
        type_="foreignkey",
    )
