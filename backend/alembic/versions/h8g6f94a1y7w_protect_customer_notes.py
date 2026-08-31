"""Protect Customer note authorship and immutable history.

Revision ID: h8g6f94a1y7w
Revises: g7f5e83z0x6v
"""

from collections.abc import Sequence

from alembic import op

revision: str = "h8g6f94a1y7w"
down_revision: str | Sequence[str] | None = "g7f5e83z0x6v"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_customer_notes_author",
        "customer_notes",
        "users",
        ["author_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_customer_notes_body_length",
        "customer_notes",
        "length(btrim(body)) BETWEEN 1 AND 4000",
    )
    op.execute(
        """
        CREATE FUNCTION prevent_customer_note_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Customer note history is immutable'
                USING ERRCODE = '23514';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_customer_notes_immutable
        BEFORE UPDATE OR DELETE ON customer_notes
        FOR EACH ROW EXECUTE FUNCTION prevent_customer_note_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_customer_notes_immutable ON customer_notes")
    op.execute("DROP FUNCTION IF EXISTS prevent_customer_note_mutation()")
    op.drop_constraint(
        "ck_customer_notes_body_length", "customer_notes", type_="check"
    )
    op.drop_constraint("fk_customer_notes_author", "customer_notes", type_="foreignkey")
