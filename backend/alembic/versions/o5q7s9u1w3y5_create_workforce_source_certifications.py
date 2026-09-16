"""Create durable Workforce source certification lineage.

Revision ID: o5q7s9u1w3y5
Revises: p5r7t9v1x3z5
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "o5q7s9u1w3y5"
down_revision: str | Sequence[str] | None = "p5r7t9v1x3z5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    decisions = "'CONFIRM','SELECT_EXISTING','CREATE_ONBOARD','HOLD','LEGACY_ONLY'"
    op.create_table(
        "workforce_source_certifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(40), nullable=False),
        sa.Column("source_employee_id", sa.String(191), nullable=False),
        sa.Column("evidence_reference", sa.String(255), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("current_decision", sa.String(32), nullable=False),
        sa.Column("current_revision", sa.Integer(), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True)),
        sa.Column("onboarding_request_id", postgresql.UUID(as_uuid=True)),
        sa.Column("decided_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"current_decision IN ({decisions})",
            name="ck_workforce_source_certification_decision",
        ),
        sa.CheckConstraint(
            "current_revision >= 1", name="ck_workforce_source_certification_revision"
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["onboarding_request_id"],
            ["identity_onboarding_requests.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_workforce_source_certification_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "employee_id"],
            ["employees.company_id", "employees.id"],
            name="fk_workforce_source_certification_employee",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "source_system",
            "source_employee_id",
            name="uq_workforce_source_certification_identity",
        ),
    )
    op.create_index(
        "uq_workforce_source_certification_active_employee",
        "workforce_source_certifications",
        ["company_id", "employee_id"],
        unique=True,
        postgresql_where=sa.text(
            "employee_id IS NOT NULL AND current_decision IN ('CONFIRM','SELECT_EXISTING')"
        ),
    )
    op.create_index(
        "uq_workforce_source_certification_active_onboarding",
        "workforce_source_certifications",
        ["company_id", "onboarding_request_id"],
        unique=True,
        postgresql_where=sa.text("onboarding_request_id IS NOT NULL"),
    )
    op.create_table(
        "workforce_source_certification_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("certification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("prior_revision_id", postgresql.UUID(as_uuid=True)),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("evidence_reference", sa.String(255), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True)),
        sa.Column("onboarding_request_id", postgresql.UUID(as_uuid=True)),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"decision IN ({decisions})", name="ck_workforce_source_revision_decision"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_workforce_source_revision_number"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["certification_id"],
            ["workforce_source_certifications.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["prior_revision_id"],
            ["workforce_source_certification_revisions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "certification_id",
            "revision",
            name="uq_workforce_source_certification_revision",
        ),
    )


def downgrade() -> None:
    op.drop_table("workforce_source_certification_revisions")
    op.drop_index(
        "uq_workforce_source_certification_active_onboarding",
        table_name="workforce_source_certifications",
    )
    op.drop_index(
        "uq_workforce_source_certification_active_employee",
        table_name="workforce_source_certifications",
    )
    op.drop_table("workforce_source_certifications")
