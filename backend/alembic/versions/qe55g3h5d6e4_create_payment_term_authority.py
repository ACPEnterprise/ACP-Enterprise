"""create payment term authority

Revision ID: qe55g3h5d6e4
Revises: pd449f2g4c5d3
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "qe55g3h5d6e4"
down_revision: str | Sequence[str] | None = "pd449f2g4c5d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payment_term_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("term_code", sa.String(32), nullable=False),
        sa.Column("net_days", sa.Integer(), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_through", sa.Date(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source_system", sa.String(80), nullable=False),
        sa.Column("source_record_id", sa.String(255), nullable=True),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "approved_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "customer_id"],
            ["customers.company_id", "customers.id"],
            name="fk_payment_term_policies_customer_scope",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "term_code IN ('COD','DUE_ON_COMPLETION','DUE_ON_RECEIPT','NET')",
            name="ck_payment_term_policies_code",
        ),
        sa.CheckConstraint(
            "(term_code = 'NET' AND net_days IS NOT NULL AND net_days > 0) OR "
            "(term_code <> 'NET' AND net_days IS NULL)",
            name="ck_payment_term_policies_net_days",
        ),
        sa.CheckConstraint("version >= 1", name="ck_payment_term_policies_version"),
        sa.CheckConstraint(
            "effective_through IS NULL OR effective_through >= effective_from",
            name="ck_payment_term_policies_effective_window",
        ),
        sa.CheckConstraint(
            "evidence_digest ~ '^[0-9a-f]{64}$'",
            name="ck_payment_term_policies_digest",
        ),
        sa.UniqueConstraint(
            "company_id",
            "customer_id",
            "version",
            name="uq_payment_term_policies_scope_version",
        ),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_payment_term_policies_command"
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_payment_term_policies_company"
        ),
    )
    op.create_index(
        "ix_payment_term_policies_resolution",
        "payment_term_policies",
        ["company_id", "customer_id", "effective_from", "version"],
    )
    op.create_index(
        "uq_payment_term_policies_company_default_version",
        "payment_term_policies",
        ["company_id", "version"],
        unique=True,
        postgresql_where=sa.text("customer_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_payment_term_policies_company_default_version",
        table_name="payment_term_policies",
    )
    op.drop_index(
        "ix_payment_term_policies_resolution", table_name="payment_term_policies"
    )
    op.drop_table("payment_term_policies")
