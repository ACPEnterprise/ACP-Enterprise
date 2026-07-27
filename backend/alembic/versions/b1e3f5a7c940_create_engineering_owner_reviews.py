"""create engineering owner reviews

Revision ID: b1e3f5a7c940
Revises: a0d2e4f6b839
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b1e3f5a7c940"
down_revision: str | None = "a0d2e4f6b839"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "engineering_execution_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("composition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_identifier", sa.String(100), nullable=False),
        sa.Column("instruction_digest", sa.String(128), nullable=False),
        sa.Column("request_digest", sa.String(128), nullable=False),
        sa.Column("composition_digest", sa.String(64), nullable=False),
        sa.Column("review_digest", sa.String(64), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "state IN ('pending','accepted','rejected')",
            name="ck_engineering_execution_reviews_state",
        ),
        sa.CheckConstraint(
            "length(review_digest) = 64",
            name="ck_engineering_execution_reviews_digest",
        ),
        sa.CheckConstraint(
            "version >= 1",
            name="ck_engineering_execution_reviews_version",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["command_id"], ["engineering_commands.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"], ["engineering_executions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["composition_id"],
            ["engineering_execution_compositions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["engineering_provider_execution_attempts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["result_id"],
            ["engineering_normalized_provider_results.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "result_id",
            name="uq_engineering_execution_reviews_result",
        ),
        sa.UniqueConstraint(
            "company_id",
            "id",
            name="uq_engineering_execution_reviews_company_id",
        ),
    )
    op.create_index(
        "ix_engineering_execution_reviews_company_state",
        "engineering_execution_reviews",
        ["company_id", "state", "created_at", "id"],
    )
    op.create_index(
        "ix_engineering_execution_reviews_company_command",
        "engineering_execution_reviews",
        ["company_id", "command_id", "created_at", "id"],
    )
    op.create_table(
        "engineering_execution_review_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("review_digest", sa.String(64), nullable=False),
        sa.Column("reason_code", sa.String(80)),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision IN ('accept','reject')",
            name="ck_engineering_review_decisions_decision",
        ),
        sa.CheckConstraint(
            "reason_code IS NULL OR length(btrim(reason_code)) BETWEEN 3 AND 80",
            name="ck_engineering_review_decisions_reason",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "review_id"],
            [
                "engineering_execution_reviews.company_id",
                "engineering_execution_reviews.id",
            ],
            name="fk_engineering_review_decisions_review",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_user_id", "company_id"],
            ["memberships.user_id", "memberships.company_id"],
            name="fk_engineering_review_decisions_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "review_id",
            name="uq_engineering_review_decisions_review",
        ),
    )
    op.create_index(
        "ix_engineering_review_decisions_company_decided",
        "engineering_execution_review_decisions",
        ["company_id", "decided_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_engineering_review_decisions_company_decided",
        table_name="engineering_execution_review_decisions",
    )
    op.drop_table("engineering_execution_review_decisions")
    op.drop_index(
        "ix_engineering_execution_reviews_company_command",
        table_name="engineering_execution_reviews",
    )
    op.drop_index(
        "ix_engineering_execution_reviews_company_state",
        table_name="engineering_execution_reviews",
    )
    op.drop_table("engineering_execution_reviews")
