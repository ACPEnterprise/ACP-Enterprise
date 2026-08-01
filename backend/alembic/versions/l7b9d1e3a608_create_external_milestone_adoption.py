"""Create external milestone adoption and evidence persistence.

Revision ID: l7b9d1e3a608
Revises: k6a8c0d2f597
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "l7b9d1e3a608"
down_revision: str | None = "k6a8c0d2f597"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "engineering_milestones",
        sa.Column(
            "externally_adoptable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_table(
        "engineering_external_milestone_adoptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("roadmap_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("milestone_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repository_key", sa.String(100), nullable=False),
        sa.Column("branch", sa.String(255), nullable=False),
        sa.Column("starting_head", sa.String(40), nullable=False),
        sa.Column("current_head", sa.String(40), nullable=False),
        sa.Column("worktree_identity", sa.String(500)),
        sa.Column("owning_external_workstream", sa.String(160), nullable=False),
        sa.Column("declared_scope", postgresql.JSONB(), nullable=False),
        sa.Column("protected_boundaries", postgresql.JSONB(), nullable=False),
        sa.Column("expected_deliverables", postgresql.JSONB(), nullable=False),
        sa.Column("validation_requirements", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_format", sa.String(80), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False),
        sa.Column("current_activity", sa.String(500)),
        sa.Column("last_evidence_at", sa.DateTime(timezone=True)),
        sa.Column("responsible_source", sa.String(160), nullable=False),
        sa.Column("adopted_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("adopted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approval_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("approval_at", sa.DateTime(timezone=True)),
        sa.Column("approval_evidence_digest", sa.String(64)),
        sa.Column("final_head", sa.String(40)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["roadmap_id"], ["engineering_roadmaps.id"]),
        sa.ForeignKeyConstraint(["milestone_id"], ["engineering_milestones.id"]),
        sa.UniqueConstraint(
            "company_id", "milestone_id", name="uq_external_adoption_milestone"
        ),
        sa.CheckConstraint("version >= 1", name="ck_external_adoption_version"),
        sa.CheckConstraint(
            "progress_percent BETWEEN 0 AND 100",
            name="ck_external_adoption_progress",
        ),
        sa.CheckConstraint(
            "status IN ('pending_start','externally_running','externally_validating','externally_blocked','waiting_review','revision_requested','completed','cancelled','archived')",
            name="ck_external_adoption_status",
        ),
    )
    op.create_index(
        "ix_external_adoption_company_status",
        "engineering_external_milestone_adoptions",
        ["company_id", "status", "updated_at"],
    )
    op.create_table(
        "engineering_external_milestone_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("adoption_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expected_adoption_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False),
        sa.Column("current_activity", sa.String(500)),
        sa.Column("starting_head", sa.String(40), nullable=False),
        sa.Column("current_head", sa.String(40), nullable=False),
        sa.Column("commits", postgresql.JSONB(), nullable=False),
        sa.Column("files_changed", postgresql.JSONB(), nullable=False),
        sa.Column("validation_results", postgresql.JSONB(), nullable=False),
        sa.Column("dependencies", postgresql.JSONB(), nullable=False),
        sa.Column("blockers", postgresql.JSONB(), nullable=False),
        sa.Column("completion_evidence", postgresql.JSONB(), nullable=False),
        sa.Column("owner_action_required", sa.Boolean(), nullable=False),
        sa.Column("repository_state", sa.String(16), nullable=False),
        sa.Column("correction", sa.Boolean(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column(
            "submitted_by_user_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(
            ["adoption_id"], ["engineering_external_milestone_adoptions.id"]
        ),
        sa.UniqueConstraint(
            "company_id",
            "adoption_id",
            "idempotency_key",
            name="uq_external_evidence_idempotency",
        ),
    )
    op.create_index(
        "ix_external_evidence_adoption_order",
        "engineering_external_milestone_evidence",
        ["company_id", "adoption_id", "occurred_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_external_evidence_adoption_order",
        table_name="engineering_external_milestone_evidence",
    )
    op.drop_table("engineering_external_milestone_evidence")
    op.drop_index(
        "ix_external_adoption_company_status",
        table_name="engineering_external_milestone_adoptions",
    )
    op.drop_table("engineering_external_milestone_adoptions")
    op.drop_column("engineering_milestones", "externally_adoptable")
