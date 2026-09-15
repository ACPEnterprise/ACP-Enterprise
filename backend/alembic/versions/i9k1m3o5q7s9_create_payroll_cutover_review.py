"""Create bounded Payroll cutover review and bridge evidence authority.

Revision ID: i9k1m3o5q7s9
Revises: h8j0l2n4p6r8
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "i9k1m3o5q7s9"
down_revision = "h8j0l2n4p6r8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payroll_cutover_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("lifecycle", sa.String(40), nullable=False),
        sa.Column("proposed_legacy_period_end", sa.Date()),
        sa.Column("proposed_acp_period_start", sa.Date()),
        sa.Column("opening_ytd_effective_date", sa.Date()),
        sa.Column(
            "created_by_user_id",
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
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_payroll_cutover_review_version"),
        sa.CheckConstraint(
            "lifecycle IN ('draft','ready_for_certification','certification_in_progress','ready_for_cutover_approval','approved')",
            name="ck_payroll_cutover_review_lifecycle",
        ),
        sa.CheckConstraint(
            "proposed_acp_period_start IS NULL OR proposed_legacy_period_end IS NULL OR proposed_acp_period_start > proposed_legacy_period_end",
            name="ck_payroll_cutover_review_boundary",
        ),
        sa.UniqueConstraint(
            "company_id", "version", name="uq_payroll_cutover_review_version"
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_payroll_cutover_review_company_id"
        ),
    )
    op.create_table(
        "payroll_cutover_fact_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True)),
        sa.Column("fact_key", sa.String(120), nullable=False),
        sa.Column("candidate_reference", postgresql.JSONB(), nullable=False),
        sa.Column("candidate_classification", sa.String(64), nullable=False),
        sa.Column("protected_envelope_id", postgresql.UUID(as_uuid=True)),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("certification_state", sa.String(24), nullable=False),
        sa.Column("certifier_role", sa.String(16), nullable=False),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("certified_at", sa.DateTime(timezone=True)),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "supersedes_revision_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("payroll_cutover_fact_revisions.id", ondelete="RESTRICT"),
        ),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "review_id"],
            ["payroll_cutover_reviews.company_id", "payroll_cutover_reviews.id"],
            ondelete="RESTRICT",
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
        sa.CheckConstraint("revision >= 1", name="ck_payroll_cutover_fact_revision"),
        sa.CheckConstraint(
            "action IN ('confirm','correct','provide','not_applicable')",
            name="ck_payroll_cutover_fact_action",
        ),
        sa.CheckConstraint(
            "certification_state IN ('draft','certified','superseded')",
            name="ck_payroll_cutover_fact_state",
        ),
        sa.CheckConstraint(
            "certifier_role IN ('owner','accountant')",
            name="ck_payroll_cutover_fact_role",
        ),
        sa.UniqueConstraint(
            "company_id",
            "review_id",
            "employee_id",
            "fact_key",
            "revision",
            name="uq_payroll_cutover_fact_revision",
        ),
        sa.UniqueConstraint(
            "company_id",
            "actor_user_id",
            "idempotency_key",
            name="uq_payroll_cutover_fact_idempotency",
        ),
        sa.UniqueConstraint(
            "supersedes_revision_id", name="uq_payroll_cutover_fact_successor"
        ),
    )
    op.create_table(
        "payroll_cutover_bridge_periods",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("pay_date", sa.Date(), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("certification_state", sa.String(32), nullable=False),
        sa.Column("source_reference", sa.String(240), nullable=False),
        sa.Column("coverage_complete", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "owner_certified_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("owner_certified_at", sa.DateTime(timezone=True)),
        sa.Column(
            "accountant_certified_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("accountant_certified_at", sa.DateTime(timezone=True)),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "period_end >= period_start", name="ck_payroll_cutover_bridge_dates"
        ),
        sa.CheckConstraint(
            "pay_date >= period_end", name="ck_payroll_cutover_bridge_paydate"
        ),
        sa.CheckConstraint(
            "source_type IN ('manual_paper_check','legacy_provider','other_certified_external')",
            name="ck_payroll_cutover_bridge_source",
        ),
        sa.CheckConstraint(
            "certification_state IN ('draft','owner_certified','accountant_certified','certified','superseded')",
            name="ck_payroll_cutover_bridge_state",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "review_id"],
            ["payroll_cutover_reviews.company_id", "payroll_cutover_reviews.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "company_id",
            "review_id",
            "period_start",
            "period_end",
            "source_type",
            name="uq_payroll_cutover_bridge_period",
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_payroll_cutover_bridge_company_id"
        ),
        sa.UniqueConstraint(
            "company_id",
            "actor_user_id",
            "idempotency_key",
            name="uq_payroll_cutover_bridge_idempotency",
        ),
    )
    op.create_table(
        "payroll_cutover_bridge_employee_fact_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bridge_period_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True)),
        sa.Column("source_employee_reference", sa.String(240)),
        sa.Column("fact_key", sa.String(120), nullable=False),
        sa.Column(
            "protected_envelope_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("certification_state", sa.String(24), nullable=False),
        sa.Column("certifier_role", sa.String(16), nullable=False),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "employee_id"],
            ["employees.company_id", "employees.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "bridge_period_id"],
            [
                "payroll_cutover_bridge_periods.company_id",
                "payroll_cutover_bridge_periods.id",
            ],
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
        sa.CheckConstraint(
            "revision >= 1", name="ck_payroll_cutover_bridge_fact_revision"
        ),
        sa.CheckConstraint(
            "certification_state IN ('draft','certified','superseded')",
            name="ck_payroll_cutover_bridge_fact_state",
        ),
        sa.UniqueConstraint(
            "company_id",
            "bridge_period_id",
            "employee_id",
            "source_employee_reference",
            "fact_key",
            "revision",
            name="uq_payroll_cutover_bridge_fact_revision",
        ),
        sa.UniqueConstraint(
            "company_id",
            "actor_user_id",
            "idempotency_key",
            name="uq_payroll_cutover_bridge_fact_idempotency",
        ),
    )


def downgrade() -> None:
    op.drop_table("payroll_cutover_bridge_employee_fact_revisions")
    op.drop_table("payroll_cutover_bridge_periods")
    op.drop_table("payroll_cutover_fact_revisions")
    op.drop_table("payroll_cutover_reviews")
