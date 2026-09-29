"""Google Ads read-only ingestion authority.

Revision ID: rg7c9e1f3i5k7
Revises: qf6b8d0e2h4j6
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "rg7c9e1f3i5k7"
down_revision: str | Sequence[str] | None = "qf6b8d0e2h4j6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB()


def base_columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
    )


def company_fk() -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["company_id"], ["companies.id"], ondelete="RESTRICT"
    )


def branch_fk() -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["company_id", "branch_id"],
        ["branches.company_id", "branches.id"],
        ondelete="RESTRICT",
    )


def upgrade() -> None:
    op.create_table(
        "platform_provider_connection_bindings",
        *base_columns(),
        sa.Column("environment", sa.String(24), nullable=False),
        sa.Column("provider_family", sa.String(80), nullable=False),
        sa.Column("client_credential_reference", sa.String(240), nullable=False),
        sa.Column("account_token_reference", sa.String(240), nullable=False),
        sa.Column("granted_scopes", JSONB, nullable=False),
        sa.Column("consent_actor_user_id", UUID),
        sa.Column("consented_at", sa.DateTime(timezone=True)),
        sa.Column("token_fingerprint", sa.String(64)),
        sa.Column("token_generation", sa.Integer()),
        sa.Column("token_expires_at", sa.DateTime(timezone=True)),
        sa.Column("callback_identity", sa.String(240), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        company_fk(),
        sa.ForeignKeyConstraint(
            ["consent_actor_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "environment IN ('development','test','preview','beta','production')",
            name="ck_provider_connection_environment",
        ),
        sa.CheckConstraint(
            "state IN ('pending_consent','active','disabled','revoked')",
            name="ck_provider_connection_state",
        ),
        sa.CheckConstraint(
            "client_credential_reference NOT LIKE '%://%' AND account_token_reference NOT LIKE '%://%'",
            name="ck_provider_connection_opaque_references",
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_provider_connection_company_id"
        ),
    )
    op.create_index(
        "ix_provider_connection_company_provider",
        "platform_provider_connection_bindings",
        ["company_id", "environment", "provider_family", "state"],
    )
    op.create_table(
        "marketing_provider_account_bindings",
        *base_columns(),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("provider_account_id", UUID, nullable=False),
        sa.Column("connection_binding_id", UUID, nullable=False),
        sa.Column("bound_by_user_id", UUID, nullable=False),
        sa.Column(
            "ingestion_enabled", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("bound_at", sa.DateTime(timezone=True), nullable=False),
        company_fk(),
        branch_fk(),
        sa.ForeignKeyConstraint(
            ["company_id", "provider_account_id"],
            [
                "marketing_provider_accounts.company_id",
                "marketing_provider_accounts.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "connection_binding_id"],
            [
                "platform_provider_connection_bindings.company_id",
                "platform_provider_connection_bindings.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["bound_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "company_id",
            "provider_account_id",
            "branch_id",
            name="uq_marketing_provider_account_binding",
        ),
    )
    op.create_table(
        "marketing_provider_cursors",
        *base_columns(),
        sa.Column("provider_account_id", UUID, nullable=False),
        sa.Column("stream", sa.String(80), nullable=False),
        sa.Column("partition_key", sa.String(160), nullable=False),
        sa.Column("watermark_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cursor_digest", sa.String(64), nullable=False),
        sa.Column("last_completed_sync_run_id", UUID, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        company_fk(),
        sa.ForeignKeyConstraint(
            ["company_id", "provider_account_id"],
            [
                "marketing_provider_accounts.company_id",
                "marketing_provider_accounts.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "last_completed_sync_run_id"],
            [
                "marketing_provider_sync_runs.company_id",
                "marketing_provider_sync_runs.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "length(cursor_digest) = 64", name="ck_marketing_cursor_digest"
        ),
        sa.UniqueConstraint(
            "company_id",
            "provider_account_id",
            "stream",
            "partition_key",
            name="uq_marketing_provider_cursor_partition",
        ),
    )
    op.create_table(
        "marketing_performance_observations",
        *base_columns(),
        sa.Column("branch_id", UUID),
        sa.Column("provider_account_id", UUID, nullable=False),
        sa.Column("provider_object_identity_id", UUID),
        sa.Column("provider_snapshot_id", UUID, nullable=False),
        sa.Column("interval_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("grain", sa.String(80), nullable=False),
        sa.Column("dimensions", JSONB, nullable=False),
        sa.Column("currency", sa.String(3)),
        sa.Column("cost_micros", sa.BigInteger()),
        sa.Column("impressions", sa.BigInteger()),
        sa.Column("clicks", sa.BigInteger()),
        sa.Column("interactions", sa.BigInteger()),
        sa.Column("calls", sa.BigInteger()),
        sa.Column("provider_conversions", sa.Numeric(20, 6)),
        sa.Column("provider_conversion_value", sa.Numeric(20, 6)),
        sa.Column("schema_version", sa.String(80), nullable=False),
        sa.Column("observation_digest", sa.String(64), nullable=False),
        company_fk(),
        branch_fk(),
        sa.ForeignKeyConstraint(
            ["company_id", "provider_account_id"],
            [
                "marketing_provider_accounts.company_id",
                "marketing_provider_accounts.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "provider_object_identity_id"],
            [
                "marketing_provider_object_identities.company_id",
                "marketing_provider_object_identities.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "provider_snapshot_id"],
            [
                "marketing_provider_snapshots.company_id",
                "marketing_provider_snapshots.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "interval_end > interval_start", name="ck_marketing_performance_interval"
        ),
        sa.CheckConstraint(
            "length(observation_digest) = 64", name="ck_marketing_performance_digest"
        ),
        sa.UniqueConstraint(
            "company_id", "observation_digest", name="uq_marketing_performance_digest"
        ),
    )
    op.create_index(
        "ix_marketing_performance_interval",
        "marketing_performance_observations",
        ["company_id", "provider_account_id", "interval_start"],
    )
    op.create_table(
        "marketing_search_term_observations",
        *base_columns(),
        sa.Column("branch_id", UUID),
        sa.Column("provider_account_id", UUID, nullable=False),
        sa.Column("provider_snapshot_id", UUID, nullable=False),
        sa.Column("campaign_identity_id", UUID),
        sa.Column("interval_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("search_term_digest", sa.String(64), nullable=False),
        sa.Column("keyword_text_digest", sa.String(64)),
        sa.Column("match_type", sa.String(40)),
        sa.Column("status", sa.String(40)),
        sa.Column("metrics", JSONB, nullable=False),
        sa.Column("dimensions", JSONB, nullable=False),
        sa.Column("schema_version", sa.String(80), nullable=False),
        sa.Column("observation_digest", sa.String(64), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        company_fk(),
        branch_fk(),
        sa.ForeignKeyConstraint(
            ["company_id", "provider_account_id"],
            [
                "marketing_provider_accounts.company_id",
                "marketing_provider_accounts.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "provider_snapshot_id"],
            [
                "marketing_provider_snapshots.company_id",
                "marketing_provider_snapshots.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "campaign_identity_id"],
            [
                "marketing_provider_object_identities.company_id",
                "marketing_provider_object_identities.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "length(search_term_digest) = 64", name="ck_marketing_search_term_digest"
        ),
        sa.CheckConstraint(
            "length(observation_digest) = 64",
            name="ck_marketing_search_observation_digest",
        ),
        sa.UniqueConstraint(
            "company_id",
            "observation_digest",
            name="uq_marketing_search_observation_digest",
        ),
    )
    op.create_table(
        "marketing_provider_reconciliation_findings",
        *base_columns(),
        sa.Column("branch_id", UUID),
        sa.Column("provider_account_id", UUID, nullable=False),
        sa.Column("sync_run_id", UUID, nullable=False),
        sa.Column("kind", sa.String(80), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("missing_components", JSONB, nullable=False),
        sa.Column("details", JSONB, nullable=False),
        sa.Column("finding_digest", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        company_fk(),
        branch_fk(),
        sa.ForeignKeyConstraint(
            ["company_id", "provider_account_id"],
            [
                "marketing_provider_accounts.company_id",
                "marketing_provider_accounts.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "sync_run_id"],
            [
                "marketing_provider_sync_runs.company_id",
                "marketing_provider_sync_runs.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "state IN ('open','resolved','not_available','accepted_gap')",
            name="ck_marketing_reconciliation_state",
        ),
        sa.UniqueConstraint(
            "company_id", "finding_digest", name="uq_marketing_reconciliation_digest"
        ),
    )
    op.create_table(
        "marketing_provider_coverage_manifests",
        *base_columns(),
        sa.Column("branch_id", UUID),
        sa.Column("provider_account_id", UUID, nullable=False),
        sa.Column("sync_run_id", UUID, nullable=False),
        sa.Column("interval_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attribution_policy_version", sa.String(80), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("coverage_percent", sa.Integer(), nullable=False),
        sa.Column("missing_components", JSONB, nullable=False),
        sa.Column("availability", sa.String(24), nullable=False),
        sa.Column("manifest_digest", sa.String(64), nullable=False),
        company_fk(),
        branch_fk(),
        sa.ForeignKeyConstraint(
            ["company_id", "provider_account_id"],
            [
                "marketing_provider_accounts.company_id",
                "marketing_provider_accounts.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "sync_run_id"],
            [
                "marketing_provider_sync_runs.company_id",
                "marketing_provider_sync_runs.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "availability IN ('complete','partial','unavailable','not_applicable')",
            name="ck_marketing_provider_coverage_availability",
        ),
        sa.CheckConstraint(
            "coverage_percent BETWEEN 0 AND 100",
            name="ck_marketing_provider_coverage_percent",
        ),
        sa.UniqueConstraint(
            "company_id",
            "manifest_digest",
            name="uq_marketing_provider_coverage_digest",
        ),
    )
    for table in (
        "marketing_performance_observations",
        "marketing_search_term_observations",
        "marketing_provider_coverage_manifests",
    ):
        op.execute(
            f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION marketing_reject_append_only_mutation()"
        )


def downgrade() -> None:
    for table in (
        "marketing_provider_coverage_manifests",
        "marketing_search_term_observations",
        "marketing_performance_observations",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only ON {table}")
    op.drop_table("marketing_provider_coverage_manifests")
    op.drop_table("marketing_provider_reconciliation_findings")
    op.drop_table("marketing_search_term_observations")
    op.drop_index(
        "ix_marketing_performance_interval",
        table_name="marketing_performance_observations",
    )
    op.drop_table("marketing_performance_observations")
    op.drop_table("marketing_provider_cursors")
    op.drop_table("marketing_provider_account_bindings")
    op.drop_index(
        "ix_provider_connection_company_provider",
        table_name="platform_provider_connection_bindings",
    )
    op.drop_table("platform_provider_connection_bindings")
