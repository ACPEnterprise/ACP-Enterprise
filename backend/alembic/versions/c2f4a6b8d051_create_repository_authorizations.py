"""create repository authorizations

Revision ID: c2f4a6b8d051
Revises: b1e3f5a7c940
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c2f4a6b8d051"
down_revision: str | None = "b1e3f5a7c940"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "engineering_repository_authorizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("capability_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_decision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "authorized_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("operation_type", sa.String(30), nullable=False),
        sa.Column("file_boundary", postgresql.JSONB(), nullable=False),
        sa.Column("expected_branch", sa.String(255), nullable=False),
        sa.Column("expected_base_commit", sa.String(40), nullable=False),
        sa.Column("review_digest", sa.String(64), nullable=False),
        sa.Column("authorization_digest", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "operation_type IN ('commit')",
            name="ck_repository_authorizations_operation",
        ),
        sa.CheckConstraint(
            "state IN ('authorized','expired','revoked','consumed')",
            name="ck_repository_authorizations_state",
        ),
        sa.CheckConstraint(
            "expected_base_commit ~ '^[0-9a-f]{40}$'",
            name="ck_repository_authorizations_base_commit",
        ),
        sa.CheckConstraint(
            "length(btrim(expected_branch)) > 0",
            name="ck_repository_authorizations_branch",
        ),
        sa.CheckConstraint(
            "jsonb_array_length(file_boundary) > 0",
            name="ck_repository_authorizations_file_boundary",
        ),
        sa.CheckConstraint(
            "length(authorization_digest) = 64",
            name="ck_repository_authorizations_digest",
        ),
        sa.CheckConstraint(
            "expires_at > authorized_at",
            name="ck_repository_authorizations_expiration",
        ),
        sa.CheckConstraint(
            "version >= 1",
            name="ck_repository_authorizations_version",
        ),
        sa.CheckConstraint(
            "(state = 'revoked') = (revoked_at IS NOT NULL)",
            name="ck_repository_authorizations_revoked",
        ),
        sa.CheckConstraint(
            "(state = 'consumed') = (consumed_at IS NOT NULL)",
            name="ck_repository_authorizations_consumed",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["command_id"], ["engineering_commands.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"], ["engineering_executions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["result_id"],
            ["engineering_normalized_provider_results.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "review_id"],
            [
                "engineering_execution_reviews.company_id",
                "engineering_execution_reviews.id",
            ],
            name="fk_repository_authorizations_review",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["review_decision_id"],
            ["engineering_execution_review_decisions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["authorized_by_user_id", "company_id"],
            ["memberships.user_id", "memberships.company_id"],
            name="fk_repository_authorizations_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "capability_id",
            name="uq_repository_authorizations_capability",
        ),
        sa.UniqueConstraint(
            "company_id",
            "idempotency_key",
            name="uq_repository_authorizations_idempotency",
        ),
        sa.UniqueConstraint(
            "company_id",
            "review_id",
            "operation_type",
            name="uq_repository_authorizations_review_operation",
        ),
        sa.UniqueConstraint(
            "company_id",
            "id",
            name="uq_repository_authorizations_company_id",
        ),
    )
    op.create_index(
        "ix_repository_authorizations_company_state",
        "engineering_repository_authorizations",
        ["company_id", "state", "expires_at", "id"],
    )
    op.create_index(
        "ix_repository_authorizations_company_command",
        "engineering_repository_authorizations",
        ["company_id", "command_id", "authorized_at", "id"],
    )
    op.create_table(
        "engineering_repository_authorization_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("authorization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(20), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("reason_code", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('requested','granted','revoked','expired','consumed')",
            name="ck_repository_authorization_events_type",
        ),
        sa.CheckConstraint(
            "state IN ('authorized','expired','revoked','consumed')",
            name="ck_repository_authorization_events_state",
        ),
        sa.CheckConstraint(
            "version >= 1",
            name="ck_repository_authorization_events_version",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "authorization_id"],
            [
                "engineering_repository_authorizations.company_id",
                "engineering_repository_authorizations.id",
            ],
            name="fk_repository_authorization_events_authorization",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id", "company_id"],
            ["memberships.user_id", "memberships.company_id"],
            name="fk_repository_authorization_events_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "authorization_id",
            "version",
            "event_type",
            name="uq_repository_authorization_events_version",
        ),
    )
    op.create_index(
        "ix_repository_authorization_events_company_created",
        "engineering_repository_authorization_events",
        ["company_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_repository_authorization_events_company_created",
        table_name="engineering_repository_authorization_events",
    )
    op.drop_table("engineering_repository_authorization_events")
    op.drop_index(
        "ix_repository_authorizations_company_command",
        table_name="engineering_repository_authorizations",
    )
    op.drop_index(
        "ix_repository_authorizations_company_state",
        table_name="engineering_repository_authorizations",
    )
    op.drop_table("engineering_repository_authorizations")
