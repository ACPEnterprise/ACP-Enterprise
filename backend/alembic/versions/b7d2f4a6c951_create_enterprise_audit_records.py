"""create enterprise audit records

Revision ID: b7d2f4a6c951
Revises: a6c9e1f4b830
Create Date: 2026-07-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b7d2f4a6c951"
down_revision: Union[str, Sequence[str], None] = "a6c9e1f4b830"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason_code", sa.String(length=100), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(btrim(action)) > 0", name="ck_audit_records_action_not_blank"
        ),
        sa.CheckConstraint(
            "length(btrim(resource_type)) > 0",
            name="ck_audit_records_resource_type_not_blank",
        ),
        sa.CheckConstraint(
            "outcome IN ('success', 'failure', 'denied')",
            name="ck_audit_records_outcome",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_records"),
    )
    op.create_index("ix_audit_records_occurred_at", "audit_records", ["occurred_at"])
    op.create_index(
        "ix_audit_records_actor_user_id_occurred_at",
        "audit_records",
        ["actor_user_id", "occurred_at"],
    )
    op.create_index(
        "ix_audit_records_company_id_occurred_at",
        "audit_records",
        ["company_id", "occurred_at"],
    )
    op.create_index(
        "ix_audit_records_action_occurred_at",
        "audit_records",
        ["action", "occurred_at"],
    )
    op.create_index(
        "ix_audit_records_resource", "audit_records", ["resource_type", "resource_id"]
    )
    op.execute(
        """
        CREATE FUNCTION prevent_audit_record_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit records are immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_records_immutable
        BEFORE UPDATE OR DELETE ON audit_records
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_record_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_records_immutable ON audit_records")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_record_mutation()")
    op.drop_index("ix_audit_records_resource", table_name="audit_records")
    op.drop_index("ix_audit_records_action_occurred_at", table_name="audit_records")
    op.drop_index("ix_audit_records_company_id_occurred_at", table_name="audit_records")
    op.drop_index(
        "ix_audit_records_actor_user_id_occurred_at", table_name="audit_records"
    )
    op.drop_index("ix_audit_records_occurred_at", table_name="audit_records")
    op.drop_table("audit_records")
