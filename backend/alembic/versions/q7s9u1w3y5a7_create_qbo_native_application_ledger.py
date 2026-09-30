"""create qbo native application ledger

Revision ID: q7s9u1w3y5a7
Revises: qf6b8d0e2h4j6
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "q7s9u1w3y5a7"
down_revision: str | tuple[str, ...] | None = "qf6b8d0e2h4j6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

U = postgresql.UUID(as_uuid=True)
TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "qbo_native_application_records",
        sa.Column("id", U, primary_key=True),
        sa.Column(
            "company_id",
            U,
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("branch_id", U),
        sa.Column("realm_id", sa.String(160), nullable=False),
        sa.Column("source_family", sa.String(80), nullable=False),
        sa.Column("provider_record_id", sa.String(191), nullable=False),
        sa.Column("provider_version", sa.String(80)),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("acquired_at", TZ, nullable=False),
        sa.Column("source_as_of", TZ),
        sa.Column("disposition", sa.String(32), nullable=False),
        sa.Column("reason_code", sa.String(100), nullable=False),
        sa.Column("explanation", sa.Text, nullable=False),
        sa.Column("native_type", sa.String(80)),
        sa.Column("native_id", U),
        sa.Column("deterministic_match_basis", sa.String(120)),
        sa.Column(
            "dependency_identities",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "display_evidence",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "applied_by_user_id",
            U,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("applied_at", TZ, nullable=False),
        sa.Column("superseded_at", TZ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "disposition IN ('APPLIED','BOUND','QUARANTINED',"
            "'PROVIDER_UNAVAILABLE','UNSUPPORTED','REJECTED_WITH_REASON')",
            name="ck_qbo_application_disposition",
        ),
        sa.CheckConstraint("version >= 1", name="ck_qbo_application_version"),
        sa.CheckConstraint(
            "length(source_digest) = 64 AND length(evidence_digest) = 64",
            name="ck_qbo_application_digests",
        ),
        sa.CheckConstraint(
            "(disposition IN ('APPLIED','BOUND')) = (native_id IS NOT NULL)",
            name="ck_qbo_application_native_result",
        ),
        sa.UniqueConstraint(
            "company_id",
            "realm_id",
            "source_family",
            "provider_record_id",
            "version",
            name="uq_qbo_application_record_version",
        ),
    )
    op.create_index(
        "uq_qbo_application_record_current",
        "qbo_native_application_records",
        ["company_id", "realm_id", "source_family", "provider_record_id"],
        unique=True,
        postgresql_where=sa.text("superseded_at IS NULL"),
    )
    op.create_index(
        "ix_qbo_application_company_family_disposition",
        "qbo_native_application_records",
        ["company_id", "source_family", "disposition"],
    )
    op.create_table(
        "qbo_native_review_items",
        sa.Column("id", U, primary_key=True),
        sa.Column(
            "company_id",
            U,
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "application_record_id",
            U,
            sa.ForeignKey("qbo_native_application_records.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_family", sa.String(80), nullable=False),
        sa.Column("provider_record_id", sa.String(191), nullable=False),
        sa.Column("reference_number", sa.String(160)),
        sa.Column("source_date", sa.String(40)),
        sa.Column("source_amount", sa.String(80)),
        sa.Column(
            "source_entity_names",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "candidate_native_ids",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "conflicting_fields",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("exact_conflict", sa.Text, nullable=False),
        sa.Column(
            "affected_dependents",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "allowed_actions",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("state", sa.String(16), nullable=False, server_default="OPEN"),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("resolved_at", TZ),
        sa.Column("resolved_by_user_id", U),
        sa.Column("resolution_note", sa.Text),
        sa.CheckConstraint(
            "state IN ('OPEN','RESOLVED','IGNORED','REJECTED')",
            name="ck_qbo_review_state",
        ),
        sa.UniqueConstraint(
            "application_record_id", name="uq_qbo_review_application"
        ),
    )
    op.create_index(
        "ix_qbo_review_company_state",
        "qbo_native_review_items",
        ["company_id", "state", "source_family"],
    )


def downgrade() -> None:
    op.drop_index("ix_qbo_review_company_state", table_name="qbo_native_review_items")
    op.drop_table("qbo_native_review_items")
    op.drop_index(
        "ix_qbo_application_company_family_disposition",
        table_name="qbo_native_application_records",
    )
    op.drop_index(
        "uq_qbo_application_record_current",
        table_name="qbo_native_application_records",
    )
    op.drop_table("qbo_native_application_records")
