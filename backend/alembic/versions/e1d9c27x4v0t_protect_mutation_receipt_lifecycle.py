"""Protect Platform mutation receipt identity and lifecycle.

Revision ID: e1d9c27x4v0t
Revises: d0c8b16w3u9s
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e1d9c27x4v0t"
down_revision: str | Sequence[str] | None = "d0c8b16w3u9s"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION protect_platform_mutation_receipt_lifecycle()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Platform mutation receipt history cannot be deleted'
                    USING ERRCODE = '23514';
            END IF;
            IF NEW.company_id IS DISTINCT FROM OLD.company_id
               OR NEW.branch_id IS DISTINCT FROM OLD.branch_id
               OR NEW.actor_user_id IS DISTINCT FROM OLD.actor_user_id
               OR NEW.operation IS DISTINCT FROM OLD.operation
               OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
               OR NEW.request_digest IS DISTINCT FROM OLD.request_digest
               OR NEW.retention_class IS DISTINCT FROM OLD.retention_class
               OR NEW.created_at IS DISTINCT FROM OLD.created_at
               OR NEW.expires_at IS DISTINCT FROM OLD.expires_at
               OR NOT (
                   (OLD.state = 'in_progress' AND NEW.state = 'completed'
                    AND OLD.result_type IS NULL
                    AND OLD.result_id IS NULL
                    AND OLD.response_status IS NULL
                    AND OLD.completed_at IS NULL
                    AND NEW.result_type IS NOT NULL
                    AND NEW.result_id IS NOT NULL
                    AND NEW.response_status IS NOT NULL
                    AND NEW.completed_at IS NOT NULL)
                   OR
                   (OLD.state = 'completed'
                    AND NEW.state = 'reconciliation_required'
                    AND NEW.result_type IS NOT DISTINCT FROM OLD.result_type
                    AND NEW.result_id IS NOT DISTINCT FROM OLD.result_id
                    AND NEW.response_status IS NOT DISTINCT FROM OLD.response_status
                    AND NEW.completed_at IS NOT DISTINCT FROM OLD.completed_at)
               ) THEN
                RAISE EXCEPTION 'Platform mutation receipt transition is invalid'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_platform_mutation_receipts_lifecycle
        BEFORE UPDATE OR DELETE ON platform_mutation_receipts
        FOR EACH ROW EXECUTE FUNCTION protect_platform_mutation_receipt_lifecycle()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_platform_mutation_receipts_lifecycle "
        "ON platform_mutation_receipts"
    )
    op.execute("DROP FUNCTION IF EXISTS protect_platform_mutation_receipt_lifecycle()")
