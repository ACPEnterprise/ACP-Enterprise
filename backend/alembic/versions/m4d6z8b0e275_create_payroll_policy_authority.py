"""create Payroll policy and compensation authority

Revision ID: m4d6z8b0e275
Revises: l3c5y7a9d164
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "m4d6z8b0e275"
down_revision: str | Sequence[str] | None = "l3c5y7a9d164"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payroll_company_policy_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("effective_start", sa.Date(), nullable=False),
        sa.Column("effective_end", sa.Date()),
        sa.Column("lifecycle", sa.String(20), nullable=False),
        sa.Column("definition_version", sa.String(80), nullable=False),
        sa.Column("definition", postgresql.JSONB(), nullable=False),
        sa.Column("decision_evidence_digest", sa.String(64), nullable=False),
        sa.Column("authority_digest", sa.String(64), nullable=False),
        sa.Column(
            "supersedes_policy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("payroll_company_policy_versions.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "drafted_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "approved_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column(
            "retired_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.Column("audit_reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("policy_version >= 1", name="ck_payroll_policy_version"),
        sa.CheckConstraint(
            "lifecycle IN ('draft','approved','superseded','retired')",
            name="ck_payroll_policy_lifecycle",
        ),
        sa.CheckConstraint(
            "effective_end IS NULL OR effective_end > effective_start",
            name="ck_payroll_policy_interval",
        ),
        sa.CheckConstraint(
            "(lifecycle = 'draft' AND approved_by_user_id IS NULL "
            "AND approved_at IS NULL) OR (lifecycle <> 'draft' "
            "AND approved_by_user_id IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_payroll_policy_approval",
        ),
        sa.UniqueConstraint(
            "company_id", "policy_version", name="uq_payroll_policy_version"
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_payroll_policy_company_id"),
    )
    op.create_index(
        "ix_payroll_policy_resolution",
        "payroll_company_policy_versions",
        ["company_id", "lifecycle", "effective_start", "effective_end"],
    )
    op.create_table(
        "payroll_compensation_authority_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("authority_version", sa.Integer(), nullable=False),
        sa.Column("effective_start", sa.Date(), nullable=False),
        sa.Column("effective_end", sa.Date()),
        sa.Column("lifecycle", sa.String(20), nullable=False),
        sa.Column("definition_version", sa.String(80), nullable=False),
        sa.Column("compensation_type", sa.String(20), nullable=False),
        sa.Column("hourly_rate", sa.Numeric(18, 4)),
        sa.Column("salary_amount", sa.Numeric(18, 2)),
        sa.Column("salary_frequency", sa.String(40)),
        sa.Column("worker_class_reference", sa.String(160)),
        sa.Column("additional_earning_types", postgresql.JSONB(), nullable=False),
        sa.Column("recurring_components", postgresql.JSONB(), nullable=False),
        sa.Column("decision_evidence_digest", sa.String(64), nullable=False),
        sa.Column("authority_digest", sa.String(64), nullable=False),
        sa.Column(
            "supersedes_authority_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "payroll_compensation_authority_versions.id", ondelete="RESTRICT"
            ),
        ),
        sa.Column(
            "drafted_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "approved_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column(
            "retired_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.Column("audit_reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "employee_id"],
            ["employees.company_id", "employees.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("authority_version >= 1", name="ck_payroll_comp_version"),
        sa.CheckConstraint(
            "lifecycle IN ('draft','approved','superseded','retired')",
            name="ck_payroll_comp_lifecycle",
        ),
        sa.CheckConstraint(
            "compensation_type IN ('hourly','salaried')",
            name="ck_payroll_comp_type",
        ),
        sa.CheckConstraint(
            "effective_end IS NULL OR effective_end > effective_start",
            name="ck_payroll_comp_interval",
        ),
        sa.CheckConstraint(
            "(compensation_type = 'hourly' AND hourly_rate > 0 "
            "AND salary_amount IS NULL AND salary_frequency IS NULL) OR "
            "(compensation_type = 'salaried' AND salary_amount > 0 "
            "AND salary_frequency IS NOT NULL AND hourly_rate IS NULL)",
            name="ck_payroll_comp_shape",
        ),
        sa.CheckConstraint(
            "(lifecycle = 'draft' AND approved_by_user_id IS NULL "
            "AND approved_at IS NULL) OR (lifecycle <> 'draft' "
            "AND approved_by_user_id IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_payroll_comp_approval",
        ),
        sa.UniqueConstraint(
            "company_id",
            "employee_id",
            "authority_version",
            name="uq_payroll_comp_version",
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_payroll_comp_company_id"),
    )
    op.create_index(
        "ix_payroll_comp_resolution",
        "payroll_compensation_authority_versions",
        ["company_id", "employee_id", "lifecycle", "effective_start", "effective_end"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_payroll_comp_resolution",
        table_name="payroll_compensation_authority_versions",
    )
    op.drop_table("payroll_compensation_authority_versions")
    op.drop_index(
        "ix_payroll_policy_resolution", table_name="payroll_company_policy_versions"
    )
    op.drop_table("payroll_company_policy_versions")
