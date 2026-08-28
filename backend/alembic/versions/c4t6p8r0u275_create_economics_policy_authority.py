"""create generic economics policy authority

Revision ID: c4t6p8r0u275
Revises: b3s5n7q9t164
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4t6p8r0u275"
down_revision: str | Sequence[str] | None = "b3s5n7q9t164"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "economics_company_policy_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True)),
        sa.Column("family_key", sa.String(100), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("strategy_key", sa.String(100), nullable=False),
        sa.Column("parameters", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_acceptance_rule_refs", postgresql.JSONB(), nullable=False),
        sa.Column("effective_start", sa.Date(), nullable=False),
        sa.Column("effective_end", sa.Date()),
        sa.Column("lifecycle", sa.String(20), nullable=False),
        sa.Column("definition_version", sa.String(80), nullable=False),
        sa.Column("decision_evidence_digest", sa.String(64), nullable=False),
        sa.Column("policy_digest", sa.String(64), nullable=False),
        sa.Column(
            "supersedes_policy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("economics_company_policy_versions.id", ondelete="RESTRICT"),
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
        sa.CheckConstraint("policy_version >= 1", name="ck_eco_policy_version"),
        sa.CheckConstraint(
            "lifecycle IN ('draft','approved','superseded','retired')",
            name="ck_eco_policy_lifecycle",
        ),
        sa.CheckConstraint(
            "effective_end IS NULL OR effective_end > effective_start",
            name="ck_eco_policy_interval",
        ),
        sa.CheckConstraint("branch_id IS NULL", name="ck_eco_policy_company_scope_v1"),
        sa.UniqueConstraint(
            "company_id",
            "family_key",
            "policy_version",
            name="uq_eco_policy_family_version",
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_eco_policy_company_id"),
    )
    op.create_index(
        "ix_eco_policy_resolution",
        "economics_company_policy_versions",
        ["company_id", "family_key", "lifecycle", "effective_start", "effective_end"],
    )
    op.create_table(
        "economics_policy_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True)),
        sa.Column("subject_identity", sa.String(200), nullable=False),
        sa.Column("reconciliation_key", sa.String(240), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("policy_ids", postgresql.JSONB(), nullable=False),
        sa.Column("policy_digests", postgresql.JSONB(), nullable=False),
        sa.Column("definition_version", sa.String(80), nullable=False),
        sa.Column("snapshot_digest", sa.String(64), nullable=False),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "branch_id IS NULL", name="ck_eco_snapshot_company_scope_v1"
        ),
        sa.UniqueConstraint(
            "company_id", "snapshot_digest", name="uq_eco_snapshot_digest"
        ),
    )
    op.create_index(
        "ix_eco_snapshot_replay",
        "economics_policy_snapshots",
        ["company_id", "subject_identity", "as_of_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_eco_snapshot_replay", table_name="economics_policy_snapshots")
    op.drop_table("economics_policy_snapshots")
    op.drop_index(
        "ix_eco_policy_resolution", table_name="economics_company_policy_versions"
    )
    op.drop_table("economics_company_policy_versions")
