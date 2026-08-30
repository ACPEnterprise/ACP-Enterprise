"""create immutable Luminary findings and owner briefings

Revision ID: g5e4c93b0f6d
Revises: f4d3b82a9e5c
"""

from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "g5e4c93b0f6d"
down_revision: str | Sequence[str] | None = "f4d3b82a9e5c"
branch_labels = None
depends_on = None

PERMISSIONS = (
    ("6f8d01d8-80db-49e5-8fc9-497664231a01", "COMPANY_LUMINARY_READ", "read"),
    ("6f8d01d8-80db-49e5-8fc9-497664231a02", "COMPANY_LUMINARY_ANALYZE", "analyze"),
)


def upgrade() -> None:
    now = datetime.now(timezone.utc)
    for permission_id, code, action in PERMISSIONS:
        op.execute(
            sa.text(
                "INSERT INTO permissions (id, code, name, description, resource, "
                "action, status, created_at, updated_at, retired_at) VALUES "
                "(:id, :code, :name, NULL, 'luminary', :action, 'active', :at, :at, NULL) "
                "ON CONFLICT (code) DO NOTHING"
            ).bindparams(
                id=UUID(permission_id),
                code=code,
                name=code.replace("_", " ").title(),
                action=action,
                at=now,
            )
        )
    op.create_table(
        "luminary_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True)),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("finding_class", sa.String(40), nullable=False),
        sa.Column("finding_type", sa.String(80), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("observations", postgresql.JSONB(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_package_digest", sa.String(64), nullable=False),
        sa.Column("confidence_percent", sa.Integer(), nullable=False),
        sa.Column("completeness", sa.String(30), nullable=False),
        sa.Column("freshness", sa.String(30), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("limitations", postgresql.JSONB(), nullable=False),
        sa.Column("investigate_next", postgresql.JSONB(), nullable=False),
        sa.Column("engine_version", sa.String(100), nullable=False),
        sa.Column("definition_version", sa.String(100), nullable=False),
        sa.Column("finding_identity", sa.String(100), nullable=False),
        sa.Column("finding_digest", sa.String(64), nullable=False),
        sa.Column("lifecycle", sa.String(20), nullable=False),
        sa.Column("supersedes_finding_id", postgresql.UUID(as_uuid=True)),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(finding_digest) = 64", name="ck_luminary_finding_digest"
        ),
        sa.CheckConstraint(
            "period_end >= period_start", name="ck_luminary_finding_period"
        ),
        sa.CheckConstraint(
            "confidence_percent between 0 and 100",
            name="ck_luminary_finding_confidence",
        ),
        sa.CheckConstraint(
            "lifecycle in ('accepted','voided')", name="ck_luminary_finding_lifecycle"
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_finding_id"], ["luminary_findings.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "finding_identity", name="uq_luminary_finding_identity"
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_luminary_finding_company_id"),
    )
    op.create_index(
        "ix_luminary_finding_scope_period",
        "luminary_findings",
        ["company_id", "branch_id", "period_start", "period_end"],
    )
    op.create_table(
        "luminary_briefings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True)),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("evidence_package_digest", sa.String(64), nullable=False),
        sa.Column("finding_ids", postgresql.JSONB(), nullable=False),
        sa.Column("finding_digests", postgresql.JSONB(), nullable=False),
        sa.Column("sections", postgresql.JSONB(), nullable=False),
        sa.Column("completeness", sa.String(30), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("engine_version", sa.String(100), nullable=False),
        sa.Column("definition_version", sa.String(100), nullable=False),
        sa.Column("briefing_identity", sa.String(100), nullable=False),
        sa.Column("briefing_digest", sa.String(64), nullable=False),
        sa.Column("supersedes_briefing_id", postgresql.UUID(as_uuid=True)),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(briefing_digest) = 64", name="ck_luminary_briefing_digest"
        ),
        sa.CheckConstraint(
            "period_end >= period_start", name="ck_luminary_briefing_period"
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_briefing_id"], ["luminary_briefings.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "briefing_identity", name="uq_luminary_briefing_identity"
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_luminary_briefing_company_id"),
    )
    op.create_index(
        "ix_luminary_briefing_scope_period",
        "luminary_briefings",
        ["company_id", "branch_id", "period_start", "period_end", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_luminary_briefing_scope_period", table_name="luminary_briefings")
    op.drop_table("luminary_briefings")
    op.drop_index("ix_luminary_finding_scope_period", table_name="luminary_findings")
    op.drop_table("luminary_findings")
    for permission_id, code, _ in reversed(PERMISSIONS):
        op.execute(
            sa.text(
                "DELETE FROM permissions WHERE id = CAST(:id AS uuid) AND code = :code"
            ).bindparams(id=permission_id, code=code)
        )
