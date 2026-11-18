"""Create provider-neutral migration factory evidence.

Revision ID: mf1a3c5e7g9i
Revises: zq9s1u3w5y7a
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "mf1a3c5e7g9i"
down_revision: str | Sequence[str] | None = "zq9s1u3w5y7a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    op.create_table(
        "migration_factory_runs",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "company_id",
            uuid,
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("factory_version", sa.String(80), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_migration_factory_run_company_id"
        ),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_migration_factory_run_replay"
        ),
    )
    op.create_table(
        "migration_factory_coverage",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("company_id", uuid, nullable=False),
        sa.Column("run_id", uuid, nullable=False),
        sa.Column("domain", sa.String(48), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("methods", jsonb, nullable=False),
        sa.Column("source_systems", jsonb, nullable=False),
        sa.Column("source_count", sa.Integer()),
        sa.Column("received_count", sa.Integer(), nullable=False),
        sa.Column("quarantined_count", sa.Integer(), nullable=False),
        sa.Column("rejected_count", sa.Integer(), nullable=False),
        sa.Column("explanation", sa.Text()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "run_id"],
            ["migration_factory_runs.company_id", "migration_factory_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "company_id", "run_id", "domain", name="uq_migration_coverage_domain"
        ),
        sa.CheckConstraint(
            "source_count IS NULL OR source_count >= 0",
            name="ck_migration_coverage_source_count",
        ),
        sa.CheckConstraint(
            "received_count >= 0 AND quarantined_count >= 0 AND rejected_count >= 0",
            name="ck_migration_coverage_counts",
        ),
    )
    op.create_table(
        "migration_factory_raw_evidence",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "company_id",
            uuid,
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_system", sa.String(32), nullable=False),
        sa.Column("object_type", sa.String(80), nullable=False),
        sa.Column("object_id", sa.String(191), nullable=False),
        sa.Column("source_timestamp", sa.DateTime(timezone=True)),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_reference", sa.String(500), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("api_version", sa.String(80), nullable=False),
        sa.Column("authority", sa.String(120), nullable=False),
        sa.Column("batch_identity", sa.String(160), nullable=False),
        sa.Column("page_identity", sa.String(160), nullable=False),
        sa.UniqueConstraint("company_id", "id", name="uq_migration_raw_company_id"),
        sa.UniqueConstraint(
            "company_id",
            "source_system",
            "object_type",
            "object_id",
            "evidence_digest",
            name="uq_migration_raw_evidence",
        ),
    )
    op.create_table(
        "migration_factory_page_checkpoints",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("company_id", uuid, nullable=False),
        sa.Column("run_id", uuid, nullable=False),
        sa.Column("source_system", sa.String(32), nullable=False),
        sa.Column("family", sa.String(80), nullable=False),
        sa.Column("page_identity", sa.String(160), nullable=False),
        sa.Column("high_water_mark", sa.String(191)),
        sa.Column("received_count", sa.Integer(), nullable=False),
        sa.Column("quarantined_count", sa.Integer(), nullable=False),
        sa.Column("terminal_page", sa.Boolean(), nullable=False),
        sa.Column("response_digest", sa.String(64), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "run_id"],
            ["migration_factory_runs.company_id", "migration_factory_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "company_id",
            "run_id",
            "source_system",
            "family",
            "page_identity",
            name="uq_migration_page_checkpoint",
        ),
    )
    op.create_table(
        "migration_factory_authority_rules",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "company_id",
            uuid,
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("domain", sa.String(48), nullable=False),
        sa.Column("field_name", sa.String(120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source_precedence", jsonb, nullable=False),
        sa.Column("rule_digest", sa.String(64), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "company_id",
            "domain",
            "field_name",
            "version",
            name="uq_migration_authority_rule_version",
        ),
        sa.UniqueConstraint("rule_digest", name="uq_migration_authority_rule_digest"),
    )
    op.create_table(
        "migration_factory_certificates",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "company_id",
            uuid,
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("run_id", uuid, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("coverage", jsonb, nullable=False),
        sa.Column("source_hashes", jsonb, nullable=False),
        sa.Column("transformation_version", sa.String(80), nullable=False),
        sa.Column("conflicts", sa.Integer(), nullable=False),
        sa.Column("unresolved_exceptions", sa.Integer(), nullable=False),
        sa.Column("zero_silent_drops", sa.Boolean(), nullable=False),
        sa.Column("certificate_digest", sa.String(64), nullable=False),
        sa.Column("certified_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "company_id", "certificate_digest", name="uq_migration_certificate_digest"
        ),
    )
    op.create_table(
        "migration_factory_delta_cursors",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "company_id",
            uuid,
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_system", sa.String(32), nullable=False),
        sa.Column("high_water_mark", sa.String(191), nullable=False),
        sa.Column("webhook_sequence", sa.String(191)),
        sa.Column("reconciliation_digest", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "company_id", "source_system", name="uq_migration_delta_cursor"
        ),
    )
    op.execute(
        """
        CREATE FUNCTION reject_migration_factory_evidence_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'migration factory evidence is immutable';
        END;
        $$
        """
    )
    for table in (
        "migration_factory_raw_evidence",
        "migration_factory_page_checkpoints",
        "migration_factory_authority_rules",
        "migration_factory_certificates",
    ):
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_migration_factory_evidence_mutation()"
        )


def downgrade() -> None:
    for table in (
        "migration_factory_delta_cursors",
        "migration_factory_certificates",
        "migration_factory_authority_rules",
        "migration_factory_page_checkpoints",
        "migration_factory_raw_evidence",
        "migration_factory_coverage",
        "migration_factory_runs",
    ):
        op.drop_table(table)
    op.execute("DROP FUNCTION reject_migration_factory_evidence_mutation()")
