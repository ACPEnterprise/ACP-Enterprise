"""create protected Payroll tax and deduction input authority

Revision ID: w4n6j8l0o275
Revises: v3m5i7k9n164
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "w4n6j8l0o275"
down_revision: str | Sequence[str] | None = "v3m5i7k9n164"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payroll_protected_input_envelopes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key_id", sa.String(80), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_payroll_protected_company_id"
        ),
    )
    op.create_table(
        "payroll_input_authority_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True)),
        sa.Column("authority_domain", sa.String(32), nullable=False),
        sa.Column("authority_key", sa.String(120), nullable=False),
        sa.Column("authority_version", sa.Integer(), nullable=False),
        sa.Column("definition_version", sa.String(80), nullable=False),
        sa.Column("applicability", sa.String(24), nullable=False),
        sa.Column("effective_start", sa.Date(), nullable=False),
        sa.Column("effective_end", sa.Date()),
        sa.Column("lifecycle", sa.String(20), nullable=False),
        sa.Column("jurisdiction_reference", sa.String(160)),
        sa.Column("calculation_basis", sa.String(80)),
        sa.Column("priority", sa.Integer()),
        sa.Column("public_parameters", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("authority_digest", sa.String(64), nullable=False),
        sa.Column("protected_envelope_id", postgresql.UUID(as_uuid=True)),
        sa.Column("supersedes_authority_id", postgresql.UUID(as_uuid=True)),
        sa.Column("drafted_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("retired_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.Column("audit_reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "authority_domain IN ('tax','deduction','employer_contribution')",
            name="ck_payroll_input_domain",
        ),
        sa.CheckConstraint(
            "lifecycle IN ('draft','approved','superseded','retired')",
            name="ck_payroll_input_lifecycle",
        ),
        sa.CheckConstraint(
            "applicability IN ('required','not_applicable')",
            name="ck_payroll_input_applicability",
        ),
        sa.CheckConstraint(
            "effective_end IS NULL OR effective_end > effective_start",
            name="ck_payroll_input_interval",
        ),
        sa.CheckConstraint(
            "(lifecycle = 'draft' AND approved_by_user_id IS NULL AND approved_at IS NULL) "
            "OR (lifecycle <> 'draft' AND approved_by_user_id IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_payroll_input_approval",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "employee_id"],
            ["employees.company_id", "employees.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "protected_envelope_id"],
            [
                "payroll_protected_input_envelopes.company_id",
                "payroll_protected_input_envelopes.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_authority_id"],
            ["payroll_input_authority_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["drafted_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["retired_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_payroll_input_company_id"
        ),
        sa.UniqueConstraint(
            "company_id",
            "employee_id",
            "authority_domain",
            "authority_key",
            "authority_version",
            name="uq_payroll_input_authority_version",
        ),
    )
    op.create_index(
        "ix_payroll_input_resolution",
        "payroll_input_authority_versions",
        [
            "company_id",
            "employee_id",
            "authority_domain",
            "authority_key",
            "lifecycle",
            "effective_start",
            "effective_end",
        ],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_payroll_input_resolution", table_name="payroll_input_authority_versions"
    )
    op.drop_table("payroll_input_authority_versions")
    op.drop_table("payroll_protected_input_envelopes")
