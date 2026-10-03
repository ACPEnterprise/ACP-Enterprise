"""create opening state AR AP control authority

Revision ID: vl2n4p6r8t0v
Revises: uk1m3o5q7s9u
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "vl2n4p6r8t0v"
down_revision: str | Sequence[str] | None = "uk1m3o5q7s9u"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accounting_opening_control_packages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("realm_id", sa.String(160), nullable=False),
        sa.Column("package_identity", sa.String(200), nullable=False),
        sa.Column("source_version", sa.String(80), nullable=False),
        sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cutoff_timezone", sa.String(80), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_manifest_digest", sa.String(64), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("total_debits", sa.Numeric(20, 4), nullable=False),
        sa.Column("total_credits", sa.Numeric(20, 4), nullable=False),
        sa.Column("ar_control_balance", sa.Numeric(20, 4)),
        sa.Column("ar_subledger_balance", sa.Numeric(20, 4)),
        sa.Column("ap_control_balance", sa.Numeric(20, 4)),
        sa.Column("ap_subledger_balance", sa.Numeric(20, 4)),
        sa.Column("evidence_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("prepared_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("applied_journal_id", postgresql.UUID(as_uuid=True)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('REVIEW_REQUIRED','READY_FOR_APPROVAL','APPROVED','APPLIED')",
            name="ck_opening_control_package_status",
        ),
        sa.CheckConstraint(
            "total_debits >= 0 AND total_credits >= 0",
            name="ck_opening_control_package_totals",
        ),
        sa.CheckConstraint("version >= 1", name="ck_opening_control_package_version"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["prepared_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["applied_journal_id"], ["accounting_journals.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_opening_control_package_company_id"
        ),
        sa.UniqueConstraint(
            "company_id",
            "realm_id",
            "package_identity",
            name="uq_opening_control_package_identity",
        ),
    )
    op.create_index(
        "ix_opening_control_package_cutoff",
        "accounting_opening_control_packages",
        ["company_id", "cutoff_at", "status"],
    )
    op.create_table(
        "accounting_opening_control_exceptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("package_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exception_identity", sa.String(200), nullable=False),
        sa.Column("control_family", sa.String(32), nullable=False),
        sa.Column("disposition", sa.String(32), nullable=False),
        sa.Column("source_identity", sa.String(200)),
        sa.Column("native_identity", sa.String(200)),
        sa.Column("source_amount", sa.Numeric(20, 4)),
        sa.Column("native_amount", sa.Numeric(20, 4)),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "disposition IN ('MATCHED','SOURCE_ONLY','ACP_ONLY','AMOUNT_DIFFERENCE','DATE_CUTOFF_DIFFERENCE','DUPLICATE','MISSING_LINK','REVIEW_REQUIRED')",
            name="ck_opening_control_exception_disposition",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "package_id"],
            [
                "accounting_opening_control_packages.company_id",
                "accounting_opening_control_packages.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "company_id",
            "package_id",
            "exception_identity",
            name="uq_opening_control_exception_identity",
        ),
    )


def downgrade() -> None:
    op.drop_table("accounting_opening_control_exceptions")
    op.drop_index(
        "ix_opening_control_package_cutoff",
        table_name="accounting_opening_control_packages",
    )
    op.drop_table("accounting_opening_control_packages")
