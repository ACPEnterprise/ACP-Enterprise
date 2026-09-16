"""Add replay-safe Price Book candidate admission provenance."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "o1q9r27h4u0v"
down_revision: str | None = "n0p8q16g3t9u"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_price_book_categories_status",
        "price_book_categories",
        type_="check",
    )
    op.add_column(
        "price_book_categories", sa.Column("position", sa.Integer(), nullable=True)
    )
    op.create_check_constraint(
        "ck_price_book_categories_status",
        "price_book_categories",
        "status IN ('draft','active','archived')",
    )
    op.create_check_constraint(
        "ck_price_book_categories_position",
        "price_book_categories",
        "position IS NULL OR position >= 1",
    )
    op.create_table(
        "price_book_candidate_admission_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("configuration_version", sa.String(120), nullable=False),
        sa.Column("packet_digest", sa.String(64), nullable=False),
        sa.Column("readiness_digest", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("result_counts", postgresql.JSONB(), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "packet_digest ~ '^[0-9a-f]{64}$'",
            name="ck_price_book_candidate_runs_digest",
        ),
        sa.CheckConstraint(
            "status IN ('completed','conflict')",
            name="ck_price_book_candidate_runs_status",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "configuration_version",
            name="uq_price_book_candidate_runs_version",
        ),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_price_book_candidate_runs_key"
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_price_book_candidate_runs_company_id"
        ),
    )
    op.create_table(
        "price_book_candidate_bindings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("admission_run_id", sa.UUID(), nullable=False),
        sa.Column("candidate_identity", sa.String(200), nullable=False),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("native_entity_id", sa.UUID()),
        sa.Column("admission_status", sa.String(20), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("source_key", sa.String(120), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("review_flags", postgresql.JSONB(), nullable=False),
        sa.Column("activation_blockers", postgresql.JSONB(), nullable=False),
        sa.Column("candidate_evidence", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "entity_type IN ('category','service')",
            name="ck_price_book_candidate_bindings_entity_type",
        ),
        sa.CheckConstraint(
            "admission_status IN ('admitted','held')",
            name="ck_price_book_candidate_bindings_status",
        ),
        sa.CheckConstraint(
            "evidence_digest ~ '^[0-9a-f]{64}$'",
            name="ck_price_book_candidate_bindings_digest",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "admission_run_id"],
            [
                "price_book_candidate_admission_runs.company_id",
                "price_book_candidate_admission_runs.id",
            ],
            name="fk_price_book_candidate_binding_run",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "candidate_identity",
            name="uq_price_book_candidate_bindings_identity",
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_price_book_candidate_bindings_company_id"
        ),
    )
    op.create_index(
        "ix_price_book_candidate_bindings_review",
        "price_book_candidate_bindings",
        ["company_id", "entity_type", "admission_status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_price_book_candidate_bindings_review",
        table_name="price_book_candidate_bindings",
    )
    op.drop_table("price_book_candidate_bindings")
    op.drop_table("price_book_candidate_admission_runs")
    op.drop_constraint(
        "ck_price_book_categories_position", "price_book_categories", type_="check"
    )
    op.drop_constraint(
        "ck_price_book_categories_status", "price_book_categories", type_="check"
    )
    op.drop_column("price_book_categories", "position")
    op.create_check_constraint(
        "ck_price_book_categories_status",
        "price_book_categories",
        "status IN ('active','archived')",
    )
