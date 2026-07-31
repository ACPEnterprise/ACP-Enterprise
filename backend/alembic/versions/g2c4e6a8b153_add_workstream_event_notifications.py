"""publish committed engineering workstream events

Revision ID: g2c4e6a8b153
Revises: g1b3d5f7a942
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "g2c4e6a8b153"
down_revision = "g1b3d5f7a942"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "engineering_workstream_events",
        sa.Column("sequence_id", sa.BigInteger(), sa.Identity(), nullable=False),
    )
    op.create_unique_constraint(
        "uq_engineering_workstream_event_sequence",
        "engineering_workstream_events",
        ["sequence_id"],
    )
    op.add_column(
        "engineering_workstream_events",
        sa.Column("worker_session_id", postgresql.UUID(as_uuid=True)),
    )
    op.create_index(
        "ix_workstream_events_company_order",
        "engineering_workstream_events",
        ["company_id", "sequence_id"],
    )
    op.execute("""
        CREATE FUNCTION notify_engineering_workstream_event() RETURNS trigger AS $$
        BEGIN
          PERFORM pg_notify(
            'engineering_workstream_events',
            json_build_object('company_id', NEW.company_id, 'event_id', NEW.id)::text
          );
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER engineering_workstream_event_committed
        AFTER INSERT ON engineering_workstream_events
        FOR EACH ROW EXECUTE FUNCTION notify_engineering_workstream_event()
    """)


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER engineering_workstream_event_committed ON engineering_workstream_events"
    )
    op.execute("DROP FUNCTION notify_engineering_workstream_event()")
    op.drop_index(
        "ix_workstream_events_company_order",
        table_name="engineering_workstream_events",
    )
    op.drop_constraint(
        "uq_engineering_workstream_event_sequence",
        "engineering_workstream_events",
        type_="unique",
    )
    op.drop_column("engineering_workstream_events", "sequence_id")
    op.drop_column("engineering_workstream_events", "worker_session_id")
