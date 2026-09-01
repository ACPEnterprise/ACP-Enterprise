"""Protect immutable Timekeeping authority from mutation.

Revision ID: i5h3g51b8z4x
Revises: h4g2f40a7y3w
"""

from alembic import op

revision = "i5h3g51b8z4x"
down_revision = "h4g2f40a7y3w"
branch_labels = None
depends_on = None

TABLES = (
    "timekeeping_pay_periods",
    "timekeeping_punch_events",
    "timekeeping_entry_revisions",
    "timekeeping_payroll_input_snapshots",
)


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION reject_timekeeping_authority_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Timekeeping authority is immutable'
                USING ERRCODE = '23514';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable "
            f"BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_timekeeping_authority_mutation()"
        )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS reject_timekeeping_authority_mutation()")
