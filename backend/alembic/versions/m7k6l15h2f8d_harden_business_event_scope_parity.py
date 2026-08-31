"""Harden null-safe Business Event delivery scope parity.

Revision ID: m7k6l15h2f8d
Revises: l6j5k04g1e7c
"""

from collections.abc import Sequence

from alembic import op

revision: str = "m7k6l15h2f8d"
down_revision: str | Sequence[str] | None = "l6j5k04g1e7c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_business_event_receipt_registered_delivery",
        "business_event_consumer_receipts",
        "business_event_deliveries",
        ["event_id", "consumer_name"],
        ["event_id", "consumer_name"],
        ondelete="RESTRICT",
    )
    op.execute(
        """
        CREATE FUNCTION protect_business_event_scope_identity() RETURNS trigger AS $$
        BEGIN
            IF NEW.company_id IS DISTINCT FROM OLD.company_id
               OR NEW.branch_id IS DISTINCT FROM OLD.branch_id THEN
                RAISE EXCEPTION 'Business Event scope is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_business_event_scope_immutable
        BEFORE UPDATE OF company_id, branch_id ON business_events
        FOR EACH ROW EXECUTE FUNCTION protect_business_event_scope_identity()
        """
    )
    op.execute(
        """
        CREATE FUNCTION validate_business_event_delivery_scope() RETURNS trigger AS $$
        DECLARE
            parent_company uuid;
            parent_branch uuid;
        BEGIN
            IF TG_OP = 'UPDATE' AND (
                NEW.event_id IS DISTINCT FROM OLD.event_id
                OR NEW.consumer_name IS DISTINCT FROM OLD.consumer_name
                OR NEW.company_id IS DISTINCT FROM OLD.company_id
                OR NEW.branch_id IS DISTINCT FROM OLD.branch_id
                OR NEW.event_version IS DISTINCT FROM OLD.event_version
            ) THEN
                RAISE EXCEPTION 'Business Event delivery identity is immutable'
                    USING ERRCODE = '23514';
            END IF;
            SELECT company_id, branch_id
              INTO parent_company, parent_branch
              FROM business_events
             WHERE id = NEW.event_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'Business Event delivery parent is missing'
                    USING ERRCODE = '23503';
            END IF;
            IF NEW.company_id IS DISTINCT FROM parent_company
               OR NEW.branch_id IS DISTINCT FROM parent_branch THEN
                RAISE EXCEPTION 'Business Event delivery scope mismatch'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_business_event_delivery_scope
        BEFORE INSERT OR UPDATE ON business_event_deliveries
        FOR EACH ROW EXECUTE FUNCTION validate_business_event_delivery_scope()
        """
    )
    op.execute(
        """
        CREATE FUNCTION validate_business_event_evidence_scope() RETURNS trigger AS $$
        DECLARE
            parent_event uuid;
            parent_consumer varchar(160);
            parent_company uuid;
            parent_branch uuid;
        BEGIN
            SELECT event_id, consumer_name, company_id, branch_id
              INTO parent_event, parent_consumer, parent_company, parent_branch
              FROM business_event_deliveries
             WHERE id = NEW.delivery_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'Business Event delivery evidence parent is missing'
                    USING ERRCODE = '23503';
            END IF;
            IF NEW.event_id IS DISTINCT FROM parent_event
               OR NEW.consumer_name IS DISTINCT FROM parent_consumer
               OR NEW.company_id IS DISTINCT FROM parent_company
               OR NEW.branch_id IS DISTINCT FROM parent_branch THEN
                RAISE EXCEPTION 'Business Event delivery evidence scope mismatch'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_business_event_evidence_scope
        BEFORE INSERT ON business_event_delivery_evidence
        FOR EACH ROW EXECUTE FUNCTION validate_business_event_evidence_scope()
        """
    )
    op.execute(
        """
        CREATE FUNCTION validate_business_event_receipt_scope() RETURNS trigger AS $$
        DECLARE
            parent_company uuid;
            parent_branch uuid;
        BEGIN
            SELECT company_id, branch_id
              INTO parent_company, parent_branch
              FROM business_events
             WHERE id = NEW.event_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'Business Event receipt parent is missing'
                    USING ERRCODE = '23503';
            END IF;
            IF NEW.company_id IS DISTINCT FROM parent_company
               OR NEW.branch_id IS DISTINCT FROM parent_branch THEN
                RAISE EXCEPTION 'Business Event receipt scope mismatch'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_business_event_receipt_scope
        BEFORE INSERT ON business_event_consumer_receipts
        FOR EACH ROW EXECUTE FUNCTION validate_business_event_receipt_scope()
        """
    )


def downgrade() -> None:
    for trigger, table in (
        ("trg_business_event_receipt_scope", "business_event_consumer_receipts"),
        ("trg_business_event_evidence_scope", "business_event_delivery_evidence"),
        ("trg_business_event_delivery_scope", "business_event_deliveries"),
        ("trg_business_event_scope_immutable", "business_events"),
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
    for function in (
        "validate_business_event_receipt_scope",
        "validate_business_event_evidence_scope",
        "validate_business_event_delivery_scope",
        "protect_business_event_scope_identity",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {function}()")
    op.drop_constraint(
        "fk_business_event_receipt_registered_delivery",
        "business_event_consumer_receipts",
        type_="foreignkey",
    )
