"""Bind notification outbox Company, actor, and source-event provenance.

Revision ID: e5d3c61x8v4t
Revises: d4c2b50w7u3s
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e5d3c61x8v4t"
down_revision: str | Sequence[str] | None = "d4c2b50w7u3s"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_notification_outbox_company",
        "notification_outbox",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_notification_outbox_actor",
        "notification_outbox",
        "users",
        ["actor_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_notification_outbox_source_event",
        "notification_outbox",
        "business_events",
        ["source_event_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute(
        """
        CREATE FUNCTION validate_notification_outbox_source_scope()
        RETURNS trigger AS $$
        DECLARE
            parent_company uuid;
            parent_branch uuid;
        BEGIN
            IF NEW.source_event_id IS NULL THEN
                RETURN NEW;
            END IF;
            SELECT company_id, branch_id
              INTO parent_company, parent_branch
              FROM business_events
             WHERE id = NEW.source_event_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'Notification source event is missing'
                    USING ERRCODE = '23503';
            END IF;
            IF NEW.company_id IS DISTINCT FROM parent_company
               OR NEW.branch_id IS DISTINCT FROM parent_branch THEN
                RAISE EXCEPTION 'Notification source event scope mismatch'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_notification_outbox_source_scope
        BEFORE INSERT OR UPDATE OF source_event_id, company_id, branch_id
        ON notification_outbox
        FOR EACH ROW EXECUTE FUNCTION validate_notification_outbox_source_scope()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_notification_outbox_source_scope "
        "ON notification_outbox"
    )
    op.execute("DROP FUNCTION IF EXISTS validate_notification_outbox_source_scope()")
    op.drop_constraint(
        "fk_notification_outbox_source_event",
        "notification_outbox",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_notification_outbox_actor",
        "notification_outbox",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_notification_outbox_company",
        "notification_outbox",
        type_="foreignkey",
    )
