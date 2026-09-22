"""create canonical Pipeline Lead authority

Revision ID: r4t6v8x0z2c5
Revises: p2r4t6v8x1z3
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "r4t6v8x0z2c5"
down_revision = "p2r4t6v8x1z3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeline_leads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True)),
        sa.Column("prospect_name", sa.String(300)),
        sa.Column("contact_phone", sa.String(40)),
        sa.Column("contact_email", sa.String(320)),
        sa.Column("lead_source", sa.String(80), nullable=False),
        sa.Column("source_detail", sa.String(300)),
        sa.Column("source_system", sa.String(80)),
        sa.Column("source_provider_id", sa.String(200)),
        sa.Column("source_version", sa.String(80)),
        sa.Column("source_observed_at", sa.DateTime(timezone=True)),
        sa.Column("service_category", sa.String(120)),
        sa.Column("service_need", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("assigned_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("stage", sa.String(40), nullable=False),
        sa.Column("first_contact_at", sa.DateTime(timezone=True)),
        sa.Column("last_action_at", sa.DateTime(timezone=True)),
        sa.Column("next_action_type", sa.String(80)),
        sa.Column("next_action_due_at", sa.DateTime(timezone=True)),
        sa.Column("contact_attempt_count", sa.Integer(), nullable=False),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True)),
        sa.Column("job_id", postgresql.UUID(as_uuid=True)),
        sa.Column("estimate_id", postgresql.UUID(as_uuid=True)),
        sa.Column("outcome", sa.String(20)),
        sa.Column("lost_reason", sa.String(200)),
        sa.Column("attributable_value_minor", sa.Integer()),
        sa.Column("value_currency", sa.String(3)),
        sa.Column("value_authority", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "stage IN ('new','contacted','qualified','appointment_needed','scheduled',"
            "'estimate_follow_up','won','lost','nurture')",
            name="ck_pipeline_leads_stage",
        ),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('won','lost','nurture')",
            name="ck_pipeline_leads_outcome",
        ),
        sa.CheckConstraint(
            "contact_attempt_count >= 0", name="ck_pipeline_leads_attempts"
        ),
        sa.CheckConstraint("version >= 1", name="ck_pipeline_leads_version"),
        sa.CheckConstraint(
            "attributable_value_minor IS NULL OR attributable_value_minor >= 0",
            name="ck_pipeline_leads_value",
        ),
        sa.CheckConstraint(
            "customer_id IS NOT NULL OR length(btrim(prospect_name)) > 0",
            name="ck_pipeline_leads_subject",
        ),
        sa.CheckConstraint(
            "stage <> 'lost' OR length(btrim(lost_reason)) > 0",
            name="ck_pipeline_leads_lost_reason",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_pipeline_leads_company_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["assigned_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["appointment_id"], ["appointments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["estimate_id"], ["estimates.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_pipeline_leads_company_id"),
    )
    op.create_index(
        "ix_pipeline_leads_queue",
        "pipeline_leads",
        ["company_id", "branch_id", "stage", "next_action_due_at"],
    )
    op.create_index(
        "ix_pipeline_leads_assignee",
        "pipeline_leads",
        ["company_id", "assigned_user_id", "next_action_due_at"],
    )
    op.create_index(
        "ix_pipeline_leads_customer",
        "pipeline_leads",
        ["company_id", "customer_id", "created_at"],
    )
    op.create_index(
        "uq_pipeline_leads_source_identity",
        "pipeline_leads",
        ["company_id", "source_system", "source_provider_id"],
        unique=True,
        postgresql_where=sa.text("source_provider_id IS NOT NULL"),
    )
    op.create_table(
        "pipeline_lead_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.String(80), nullable=False),
        sa.Column("from_stage", sa.String(40)),
        sa.Column("to_stage", sa.String(40)),
        sa.Column("detail", sa.String(500)),
        sa.Column("idempotency_key", sa.String(200)),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["lead_id"], ["pipeline_leads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "company_id",
            "lead_id",
            "idempotency_key",
            name="uq_pipeline_history_idempotency",
        ),
    )
    op.create_index(
        "ix_pipeline_lead_history_lead",
        "pipeline_lead_history",
        ["company_id", "lead_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_table("pipeline_lead_history")
    op.drop_table("pipeline_leads")
