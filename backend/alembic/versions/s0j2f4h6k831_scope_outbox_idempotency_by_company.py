"""scope notification outbox idempotency by Company

Revision ID: s0j2f4h6k831
Revises: r9i1e3g5j720
"""

from collections.abc import Sequence

from alembic import op

revision: str = "s0j2f4h6k831"
down_revision: str | Sequence[str] | None = "r9i1e3g5j720"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The former global constraint already prevents duplicate keys, but retain an
    # explicit fail-closed preflight so this corrective migration never repairs
    # or discards authoritative intent rows silently.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM notification_outbox
                GROUP BY company_id, idempotency_key
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION
                    'notification outbox contains duplicate tenant idempotency identities';
            END IF;
        END $$
    """)
    op.drop_constraint(
        "uq_notification_outbox_idempotency_key",
        "notification_outbox",
        type_="unique",
    )
    op.create_index(
        "uq_notification_outbox_company_idempotency_key",
        "notification_outbox",
        ["company_id", "idempotency_key"],
        unique=True,
        postgresql_where="company_id IS NOT NULL",
    )
    # Historical platform-global intents remain exactly-once within their
    # explicit unscoped namespace. New tenant producers always bind Company.
    op.create_index(
        "uq_notification_outbox_unscoped_idempotency_key",
        "notification_outbox",
        ["idempotency_key"],
        unique=True,
        postgresql_where="company_id IS NULL",
    )


def downgrade() -> None:
    # A global key can be restored only while no cross-Company reuse exists.
    # Fail closed instead of deleting or rewriting tenant-owned intent history.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM notification_outbox
                GROUP BY idempotency_key
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION
                    'tenant-scoped outbox identities cannot be collapsed globally';
            END IF;
        END $$
    """)
    op.drop_index(
        "uq_notification_outbox_unscoped_idempotency_key",
        table_name="notification_outbox",
    )
    op.drop_index(
        "uq_notification_outbox_company_idempotency_key",
        table_name="notification_outbox",
    )
    op.create_unique_constraint(
        "uq_notification_outbox_idempotency_key",
        "notification_outbox",
        ["idempotency_key"],
    )
