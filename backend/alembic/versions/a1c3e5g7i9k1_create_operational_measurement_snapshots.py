"""create immutable operational measurement snapshots

Revision ID: a1c3e5g7i9k1
Revises: z7q9m1o3r508
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1c3e5g7i9k1"
down_revision: str | Sequence[str] | None = "z7q9m1o3r508"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "economics_operational_measurement_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True)),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("contract_version", sa.String(80), nullable=False),
        sa.Column("facts", postgresql.JSONB(), nullable=False),
        sa.Column("attribution", postgresql.JSONB(), nullable=False),
        sa.Column("source_matrix", postgresql.JSONB(), nullable=False),
        sa.Column("completeness", postgresql.JSONB(), nullable=False),
        sa.Column("snapshot_digest", sa.String(64), nullable=False),
        sa.Column("predecessor_snapshot_id", postgresql.UUID(as_uuid=True)),
        sa.Column("correction_reason", sa.Text()),
        sa.Column("source_version_digest", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "period_end >= period_start", name="ck_eco_measurement_period"
        ),
        sa.CheckConstraint(
            "(predecessor_snapshot_id IS NULL AND correction_reason IS NULL) OR "
            "(predecessor_snapshot_id IS NOT NULL AND length(btrim(correction_reason)) > 0)",
            name="ck_eco_measurement_correction",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "predecessor_snapshot_id"],
            [
                "economics_operational_measurement_snapshots.company_id",
                "economics_operational_measurement_snapshots.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "company_id", "snapshot_digest", name="uq_eco_measurement_snapshot_digest"
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_eco_measurement_company_id"
        ),
        sa.UniqueConstraint(
            "predecessor_snapshot_id", name="uq_eco_measurement_successor"
        ),
    )
    op.create_index(
        "ix_eco_measurement_period",
        "economics_operational_measurement_snapshots",
        ["company_id", "branch_id", "period_start", "period_end"],
    )
    op.execute("""
        CREATE FUNCTION acp_reject_operational_measurement_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          RAISE EXCEPTION 'immutable operational measurement evidence';
        END $$
    """)
    op.execute("""
        CREATE TRIGGER trg_eco_measurement_immutable BEFORE UPDATE OR DELETE
        ON economics_operational_measurement_snapshots FOR EACH ROW
        EXECUTE FUNCTION acp_reject_operational_measurement_mutation()
    """)


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_eco_measurement_immutable ON economics_operational_measurement_snapshots"
    )
    op.execute("DROP FUNCTION IF EXISTS acp_reject_operational_measurement_mutation()")
    op.drop_index(
        "ix_eco_measurement_period",
        table_name="economics_operational_measurement_snapshots",
    )
    op.drop_table("economics_operational_measurement_snapshots")
