"""Create isolated sales demo control, scenario, and feedback authority."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "dm1v1a3c5e7g"
down_revision = "zq9s1u3w5y7c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "demo_environments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "active_company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
        ),
        sa.Column("generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("seed_version", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reset_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('provisioning','ready','resetting','disabled')",
            name="ck_demo_environment_status",
        ),
        sa.UniqueConstraint("owner_user_id", name="uq_demo_environment_owner"),
    )
    op.create_table(
        "demo_scenarios",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "environment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("demo_environments.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("guided_steps", postgresql.JSONB(), nullable=False),
        sa.Column("condition", postgresql.JSONB(), nullable=False),
        sa.Column("record_refs", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("company_id", "code", name="uq_demo_scenario_company_code"),
    )
    op.create_index(
        "ix_demo_scenario_company_position",
        "demo_scenarios",
        ["company_id", "position"],
    )
    op.create_table(
        "demo_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "environment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("demo_environments.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("page", sa.String(240), nullable=False),
        sa.Column("scenario_code", sa.String(80)),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("app_sha", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "category IN ('confusing','bug','missing_feature','customer_objection','sales_idea')",
            name="ck_demo_feedback_category",
        ),
    )
    op.create_index(
        "ix_demo_feedback_company_created",
        "demo_feedback",
        ["company_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("demo_feedback")
    op.drop_table("demo_scenarios")
    op.drop_table("demo_environments")
