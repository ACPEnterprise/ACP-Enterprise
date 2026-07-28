"""Add migration-owned Customer adapter staging.

Revision ID: d5a1b7c9f263
Revises: c4f0a6b8e152
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d5a1b7c9f263"
down_revision: str | Sequence[str] | None = "c4f0a6b8e152"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customer_migration_source_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(length=50), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=100), nullable=False),
        sa.Column("transformation_sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("byte_size >= 0", name="ck_customer_source_artifact_size"),
        sa.CheckConstraint("row_count >= 0", name="ck_customer_source_artifact_rows"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "branch_id",
            "source_system",
            "source_sha256",
            name="uq_customer_migration_source_artifact",
        ),
    )
    op.create_table(
        "customer_migration_source_rows",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("source_identity", sa.String(length=191), nullable=True),
        sa.Column("source_id_sha256", sa.String(length=64), nullable=True),
        sa.Column("source_row_sha256", sa.String(length=64), nullable=False),
        sa.Column("disposition", sa.String(length=20), nullable=False),
        sa.Column("reason_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("row_number >= 2", name="ck_customer_source_row_number"),
        sa.CheckConstraint(
            "disposition IN ('accepted', 'rejected', 'duplicate')",
            name="ck_customer_source_row_disposition",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            ["customer_migration_source_artifacts.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "artifact_id", "row_number", name="uq_customer_source_row_artifact_row"
        ),
    )
    op.create_index(
        "ix_customer_source_rows_artifact_disposition",
        "customer_migration_source_rows",
        ["artifact_id", "disposition"],
    )
    op.create_table(
        "customer_migration_staging_runs",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reused_staging", sa.Boolean(), nullable=False),
        sa.Column("customers_proposed", sa.Integer(), nullable=False),
        sa.Column("contacts_proposed", sa.Integer(), nullable=False),
        sa.Column("service_locations_proposed", sa.Integer(), nullable=False),
        sa.Column("billing_addresses_proposed", sa.Integer(), nullable=False),
        sa.Column("child_exception_count", sa.Integer(), nullable=False),
        sa.Column("unmapped_field_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "customers_proposed >= 0 AND contacts_proposed >= 0 "
            "AND service_locations_proposed >= 0 "
            "AND billing_addresses_proposed >= 0 AND child_exception_count >= 0 "
            "AND unmapped_field_count >= 0",
            name="ck_customer_staging_run_counts_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            ["customer_migration_source_artifacts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["customer_migration_runs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_table(
        "customer_migration_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_row_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=30), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "entity_type IN ('customer', 'contact', 'service_location', "
            "'billing_address')",
            name="ck_customer_migration_candidate_entity",
        ),
        sa.CheckConstraint("ordinal >= 0", name="ck_customer_candidate_ordinal"),
        sa.ForeignKeyConstraint(
            ["source_row_id"],
            ["customer_migration_source_rows.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_row_id",
            "entity_type",
            "ordinal",
            name="uq_customer_candidate_source_entity_ordinal",
        ),
    )
    op.create_table(
        "customer_migration_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_row_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_type", sa.String(length=40), nullable=False),
        sa.Column("evidence_key", sa.String(length=191), nullable=False),
        sa.Column("evidence_sha256", sa.String(length=64), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "evidence_type IN ('unmapped_field', 'incomplete_address_group')",
            name="ck_customer_migration_evidence_type",
        ),
        sa.ForeignKeyConstraint(
            ["source_row_id"],
            ["customer_migration_source_rows.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_row_id",
            "evidence_type",
            "evidence_key",
            name="uq_customer_migration_evidence_source_key",
        ),
    )
    op.create_table(
        "customer_migration_child_exceptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_row_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id_sha256", sa.String(length=64), nullable=False),
        sa.Column("contract_version", sa.String(length=100), nullable=False),
        sa.Column("address_group_number", sa.Integer(), nullable=False),
        sa.Column("missing_fields", postgresql.JSONB(), nullable=False),
        sa.Column("reason_code", sa.String(length=80), nullable=False),
        sa.Column("evidence_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_row_id"],
            ["customer_migration_source_rows.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_row_id",
            "reason_code",
            "address_group_number",
            name="uq_customer_child_exception_source_group",
        ),
    )


def downgrade() -> None:
    op.drop_table("customer_migration_child_exceptions")
    op.drop_table("customer_migration_evidence")
    op.drop_table("customer_migration_candidates")
    op.drop_table("customer_migration_staging_runs")
    op.drop_index(
        "ix_customer_source_rows_artifact_disposition",
        table_name="customer_migration_source_rows",
    )
    op.drop_table("customer_migration_source_rows")
    op.drop_table("customer_migration_source_artifacts")
