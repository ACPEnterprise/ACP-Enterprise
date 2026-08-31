"""Bind Business Event ordered-consumer cursors to exact event authority.

Revision ID: f6e4d72y9w5u
Revises: e5d3c61x8v4t
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f6e4d72y9w5u"
down_revision: str | Sequence[str] | None = "e5d3c61x8v4t"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_business_event_receipt_outcome_digest",
        "business_event_consumer_receipts",
        "length(outcome_digest) = 64",
    )
    op.create_check_constraint(
        "ck_business_event_receipt_aggregate_sequence",
        "business_event_consumer_receipts",
        "aggregate_sequence IS NULL OR aggregate_sequence >= 1",
    )
    op.create_check_constraint(
        "ck_business_event_cursor_consumer_not_blank",
        "business_event_consumer_cursors",
        "length(btrim(consumer_name)) > 0",
    )
    op.create_check_constraint(
        "ck_business_event_cursor_entity_type_not_blank",
        "business_event_consumer_cursors",
        "length(btrim(entity_type)) > 0",
    )
    op.create_check_constraint(
        "ck_business_event_cursor_last_sequence",
        "business_event_consumer_cursors",
        "last_sequence >= 1",
    )
    op.execute(
        """
        CREATE FUNCTION validate_business_event_consumer_cursor()
        RETURNS trigger AS $$
        DECLARE
            parent_entity_type varchar(100);
            parent_entity_id uuid;
            parent_sequence_text text;
        BEGIN
            SELECT entity_type, entity_id, payload ->> 'aggregate_sequence'
              INTO parent_entity_type, parent_entity_id, parent_sequence_text
              FROM business_events
             WHERE id = NEW.last_event_id
               AND company_id = NEW.company_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'Business Event cursor parent is missing'
                    USING ERRCODE = '23503';
            END IF;
            IF NEW.entity_type IS DISTINCT FROM parent_entity_type
               OR NEW.entity_id IS DISTINCT FROM parent_entity_id
               OR parent_sequence_text IS NULL
               OR parent_sequence_text !~ '^[1-9][0-9]*$'
               OR NEW.last_sequence IS DISTINCT FROM parent_sequence_text::bigint THEN
                RAISE EXCEPTION 'Business Event cursor authority mismatch'
                    USING ERRCODE = '23514';
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM business_event_deliveries
                 WHERE event_id = NEW.last_event_id
                   AND consumer_name = NEW.consumer_name
            ) THEN
                RAISE EXCEPTION 'Business Event cursor consumer is unregistered'
                    USING ERRCODE = '23503';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_business_event_consumer_cursor_authority
        BEFORE INSERT OR UPDATE ON business_event_consumer_cursors
        FOR EACH ROW EXECUTE FUNCTION validate_business_event_consumer_cursor()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_business_event_consumer_cursor_authority "
        "ON business_event_consumer_cursors"
    )
    op.execute("DROP FUNCTION IF EXISTS validate_business_event_consumer_cursor()")
    for constraint, table in (
        ("ck_business_event_cursor_last_sequence", "business_event_consumer_cursors"),
        (
            "ck_business_event_cursor_entity_type_not_blank",
            "business_event_consumer_cursors",
        ),
        (
            "ck_business_event_cursor_consumer_not_blank",
            "business_event_consumer_cursors",
        ),
        (
            "ck_business_event_receipt_aggregate_sequence",
            "business_event_consumer_receipts",
        ),
        (
            "ck_business_event_receipt_outcome_digest",
            "business_event_consumer_receipts",
        ),
    ):
        op.drop_constraint(constraint, table, type_="check")
