"""Create non-operational historical workforce identity ledger.

Revision ID: zq9s1u3w5y7b
Revises: zq9s1u3w5y7a
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "zq9s1u3w5y7b"
down_revision: str | Sequence[str] | None = "zq9s1u3w5y7a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "historical_workforce_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "native_employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="RESTRICT"),
        ),
        sa.Column("source_system", sa.String(40), nullable=False),
        sa.Column("source_identity", sa.String(191), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("source_status", sa.String(80)),
        sa.Column("lifecycle_state", sa.String(20), nullable=False),
        sa.Column("provenance_reference", sa.String(500), nullable=False),
        sa.Column("evidence_digest", sa.String(64)),
        sa.Column("unresolved_reason", sa.Text()),
        sa.Column(
            "operational_access_enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "evidence_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "lifecycle_state IN ('VERIFIED','PARTIAL','QUARANTINED','UNRESOLVED')",
            name="ck_historical_workforce_lifecycle_state",
        ),
        sa.CheckConstraint(
            "operational_access_enabled = false",
            name="ck_historical_workforce_non_operational",
        ),
        sa.UniqueConstraint(
            "company_id",
            "source_system",
            "source_identity",
            name="uq_historical_workforce_source_identity",
        ),
    )
    op.create_index(
        "ix_historical_workforce_company_state",
        "historical_workforce_identities",
        ["company_id", "lifecycle_state"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_historical_workforce_company_state",
        table_name="historical_workforce_identities",
    )
    op.drop_table("historical_workforce_identities")
