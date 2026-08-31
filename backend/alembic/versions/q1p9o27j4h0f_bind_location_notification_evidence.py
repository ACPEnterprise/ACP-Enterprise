"""Bind location successors and notification delivery evidence.

Revision ID: q1p9o27j4h0f
Revises: n8l7m26i3g9e
"""

from collections.abc import Sequence

from alembic import op

revision: str = "q1p9o27j4h0f"
down_revision: str | Sequence[str] | None = "n8l7m26i3g9e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "service_location_identity_evidence_prior_evidence_id_fkey",
        "service_location_identity_evidence",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_location_identity_evidence_prior_company",
        "service_location_identity_evidence",
        "service_location_identity_evidence",
        ["prior_evidence_id", "company_id"],
        ["id", "company_id"],
        ondelete="RESTRICT",
    )

    op.execute(
        """
        CREATE FUNCTION validate_notification_delivery_evidence_scope()
        RETURNS trigger AS $$
        DECLARE
            parent_company uuid;
            parent_branch uuid;
        BEGIN
            SELECT company_id, branch_id
              INTO parent_company, parent_branch
              FROM notification_outbox
             WHERE id = NEW.outbox_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'Notification delivery evidence parent is missing'
                    USING ERRCODE = '23503';
            END IF;
            IF NEW.company_id IS DISTINCT FROM parent_company
               OR NEW.branch_id IS DISTINCT FROM parent_branch THEN
                RAISE EXCEPTION 'Notification delivery evidence scope mismatch'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_notification_delivery_evidence_scope
        BEFORE INSERT ON notification_delivery_evidence
        FOR EACH ROW EXECUTE FUNCTION validate_notification_delivery_evidence_scope()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_notification_delivery_evidence_scope "
        "ON notification_delivery_evidence"
    )
    op.execute("DROP FUNCTION IF EXISTS validate_notification_delivery_evidence_scope()")

    op.drop_constraint(
        "fk_location_identity_evidence_prior_company",
        "service_location_identity_evidence",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "service_location_identity_evidence_prior_evidence_id_fkey",
        "service_location_identity_evidence",
        "service_location_identity_evidence",
        ["prior_evidence_id"],
        ["id"],
        ondelete="RESTRICT",
    )
