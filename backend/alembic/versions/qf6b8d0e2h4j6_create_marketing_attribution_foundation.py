"""create Marketing attribution foundation

Revision ID: qf6b8d0e2h4j6
Revises: pf6b8d0f2h4j6
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "qf6b8d0e2h4j6"
down_revision: str | Sequence[str] | None = "pf6b8d0f2h4j6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def identity_columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
    )


def company_fk() -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["company_id"], ["companies.id"], ondelete="RESTRICT"
    )


def upgrade() -> None:
    op.create_table(
        "marketing_channels",
        *identity_columns(),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        company_fk(),
        sa.CheckConstraint(
            "length(btrim(code)) > 0", name="ck_marketing_channels_code"
        ),
        sa.UniqueConstraint("company_id", "code", name="uq_marketing_channels_code"),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_marketing_channels_company_id"
        ),
    )
    op.create_table(
        "marketing_sources",
        *identity_columns(),
        sa.Column("channel_id", UUID, nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("provider_family", sa.String(80)),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        company_fk(),
        sa.ForeignKeyConstraint(
            ["company_id", "channel_id"],
            ["marketing_channels.company_id", "marketing_channels.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("company_id", "code", name="uq_marketing_sources_code"),
        sa.UniqueConstraint("company_id", "id", name="uq_marketing_sources_company_id"),
    )
    op.create_table(
        "marketing_provider_accounts",
        *identity_columns(),
        sa.Column("provider_family", sa.String(80), nullable=False),
        sa.Column("external_account_id", sa.String(191), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("timezone", sa.String(100)),
        sa.Column("currency", sa.String(3)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        company_fk(),
        sa.CheckConstraint(
            "state IN ('configured','active','paused','disconnected')",
            name="ck_marketing_provider_accounts_state",
        ),
        sa.UniqueConstraint(
            "company_id",
            "provider_family",
            "external_account_id",
            name="uq_marketing_provider_accounts_external",
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_marketing_provider_accounts_company_id"
        ),
    )
    op.create_table(
        "marketing_provider_object_identities",
        *identity_columns(),
        sa.Column("provider_account_id", UUID, nullable=False),
        sa.Column("object_type", sa.String(80), nullable=False),
        sa.Column("external_object_id", sa.String(191), nullable=False),
        sa.Column("external_version", sa.String(100)),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        company_fk(),
        sa.ForeignKeyConstraint(
            ["company_id", "provider_account_id"],
            [
                "marketing_provider_accounts.company_id",
                "marketing_provider_accounts.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "company_id",
            "provider_account_id",
            "object_type",
            "external_object_id",
            name="uq_marketing_provider_objects_external",
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_marketing_provider_objects_company_id"
        ),
    )
    op.create_table(
        "marketing_campaigns",
        *identity_columns(),
        sa.Column("source_id", UUID, nullable=False),
        sa.Column("provider_object_identity_id", UUID),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        company_fk(),
        sa.ForeignKeyConstraint(
            ["company_id", "source_id"],
            ["marketing_sources.company_id", "marketing_sources.id"],
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
        sa.CheckConstraint(
            "state IN ('unknown','active','paused','ended')",
            name="ck_marketing_campaigns_state",
        ),
        sa.UniqueConstraint(
            "company_id",
            "provider_object_identity_id",
            name="uq_marketing_campaigns_provider_object",
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_marketing_campaigns_company_id"
        ),
    )
    op.create_table(
        "marketing_landing_pages",
        *identity_columns(),
        sa.Column("normalized_url", sa.String(1000), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("path", sa.String(1000), nullable=False),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        company_fk(),
        sa.UniqueConstraint(
            "company_id", "normalized_url", name="uq_marketing_landing_pages_url"
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_marketing_landing_pages_company_id"
        ),
    )
    op.create_table(
        "marketing_provider_sync_runs",
        *identity_columns(),
        sa.Column("provider_account_id", UUID, nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("adapter_version", sa.String(100), nullable=False),
        sa.Column("provider_api_version", sa.String(100)),
        sa.Column("requested_start_at", sa.DateTime(timezone=True)),
        sa.Column("requested_end_at", sa.DateTime(timezone=True)),
        sa.Column("cursor_digest", sa.String(64)),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("exception_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        company_fk(),
        sa.ForeignKeyConstraint(
            ["company_id", "provider_account_id"],
            [
                "marketing_provider_accounts.company_id",
                "marketing_provider_accounts.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('started','completed','completed_with_exceptions','failed')",
            name="ck_marketing_sync_runs_status",
        ),
        sa.CheckConstraint(
            "record_count >= 0 AND exception_count >= 0",
            name="ck_marketing_sync_runs_counts",
        ),
        sa.UniqueConstraint(
            "company_id",
            "provider_account_id",
            "idempotency_key",
            name="uq_marketing_sync_runs_idempotency",
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_marketing_sync_runs_company_id"
        ),
    )
    op.create_table(
        "marketing_provider_snapshots",
        *identity_columns(),
        sa.Column("provider_account_id", UUID, nullable=False),
        sa.Column("sync_run_id", UUID, nullable=False),
        sa.Column("provider_object_identity_id", UUID),
        sa.Column("object_type", sa.String(80), nullable=False),
        sa.Column("external_object_id", sa.String(191), nullable=False),
        sa.Column("provider_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.String(100), nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("normalized_payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
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
            ["company_id", "sync_run_id"],
            [
                "marketing_provider_sync_runs.company_id",
                "marketing_provider_sync_runs.id",
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
        sa.CheckConstraint(
            "length(payload_digest) = 64", name="ck_marketing_snapshots_digest"
        ),
        sa.UniqueConstraint(
            "company_id",
            "provider_account_id",
            "object_type",
            "external_object_id",
            "provider_as_of",
            "schema_version",
            "payload_digest",
            name="uq_marketing_snapshots_revision",
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_marketing_snapshots_company_id"
        ),
    )
    op.create_index(
        "ix_marketing_snapshots_object_as_of",
        "marketing_provider_snapshots",
        [
            "company_id",
            "provider_account_id",
            "object_type",
            "external_object_id",
            "provider_as_of",
        ],
    )
    op.create_table(
        "marketing_touches",
        *identity_columns(),
        sa.Column("branch_id", UUID),
        sa.Column("source_id", UUID),
        sa.Column("campaign_id", UUID),
        sa.Column("landing_page_id", UUID),
        sa.Column("provider_snapshot_id", UUID),
        sa.Column("evidence_kind", sa.String(80), nullable=False),
        sa.Column("resolution", sa.String(24), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("utm_source", sa.String(200)),
        sa.Column("utm_medium", sa.String(200)),
        sa.Column("utm_campaign", sa.String(240)),
        sa.Column("referrer_origin", sa.String(500)),
        sa.Column("click_id_kind", sa.String(40)),
        sa.Column("click_id_digest", sa.String(64)),
        sa.Column("tracking_reference_digest", sa.String(64)),
        sa.Column("legacy_source_value", sa.String(100)),
        sa.Column("provenance", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        company_fk(),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "source_id"],
            ["marketing_sources.company_id", "marketing_sources.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "campaign_id"],
            ["marketing_campaigns.company_id", "marketing_campaigns.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "landing_page_id"],
            ["marketing_landing_pages.company_id", "marketing_landing_pages.id"],
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
            "resolution IN ('resolved','unknown','conflicting','not_available')",
            name="ck_marketing_touches_resolution",
        ),
        sa.CheckConstraint(
            "length(evidence_digest) = 64", name="ck_marketing_touches_digest"
        ),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_marketing_touches_idempotency"
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_marketing_touches_company_id"),
    )
    op.create_index(
        "ix_marketing_touches_observed",
        "marketing_touches",
        ["company_id", "branch_id", "observed_at", "id"],
    )
    op.create_index(
        "ix_marketing_touches_resolution",
        "marketing_touches",
        ["company_id", "resolution", "observed_at"],
    )
    op.create_table(
        "marketing_attribution_assignments",
        *identity_columns(),
        sa.Column("branch_id", UUID),
        sa.Column("touch_id", UUID),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("resolution", sa.String(24), nullable=False),
        sa.Column("supporting_evidence_reference", sa.String(300), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("actor_user_id", UUID),
        sa.Column("supersedes_assignment_id", UUID),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        company_fk(),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "touch_id"],
            ["marketing_touches.company_id", "marketing_touches.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "supersedes_assignment_id"],
            [
                "marketing_attribution_assignments.company_id",
                "marketing_attribution_assignments.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "role IN ('first_touch','latest_touch','booking','job_associated')",
            name="ck_marketing_attribution_role",
        ),
        sa.CheckConstraint(
            "method IN ('observed','provider_reported','manually_confirmed','legacy_import')",
            name="ck_marketing_attribution_method",
        ),
        sa.CheckConstraint(
            "resolution IN ('resolved','unknown','conflicting','not_available')",
            name="ck_marketing_attribution_resolution",
        ),
        sa.CheckConstraint(
            "method <> 'manually_confirmed' OR (actor_user_id IS NOT NULL AND length(btrim(reason)) > 0)",
            name="ck_marketing_attribution_manual_reason",
        ),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_marketing_attribution_idempotency"
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_marketing_attribution_company_id"
        ),
        sa.UniqueConstraint(
            "company_id",
            "branch_id",
            "id",
            name="uq_marketing_attribution_company_branch_id",
        ),
    )
    op.create_index(
        "ix_marketing_attribution_resolution",
        "marketing_attribution_assignments",
        ["company_id", "resolution", "assigned_at"],
    )

    link_specs = (
        (
            "marketing_customer_attributions",
            "customer_id",
            "customers",
            ["company_id", "customer_id"],
            ["company_id", "id"],
            False,
        ),
        (
            "marketing_lead_attributions",
            "lead_id",
            "pipeline_leads",
            ["company_id", "branch_id", "lead_id"],
            ["company_id", "branch_id", "id"],
            True,
        ),
        (
            "marketing_appointment_attributions",
            "appointment_id",
            "appointments",
            ["company_id", "branch_id", "appointment_id"],
            ["company_id", "branch_id", "id"],
            True,
        ),
        (
            "marketing_job_attributions",
            "job_id",
            "jobs",
            ["company_id", "branch_id", "job_id"],
            ["company_id", "branch_id", "id"],
            True,
        ),
    )
    for (
        table,
        target_column,
        target_table,
        local_target,
        remote_target,
        branch_required,
    ) in link_specs:
        assignment_local = (
            ["company_id", "branch_id", "assignment_id"]
            if branch_required
            else ["company_id", "assignment_id"]
        )
        assignment_remote = (
            ["company_id", "branch_id", "id"]
            if branch_required
            else ["company_id", "id"]
        )
        op.create_table(
            table,
            sa.Column("assignment_id", UUID, primary_key=True),
            sa.Column("company_id", UUID, nullable=False),
            sa.Column("branch_id", UUID, nullable=True),
            sa.Column(target_column, UUID, nullable=False),
            sa.ForeignKeyConstraint(
                assignment_local,
                [
                    f"marketing_attribution_assignments.{item}"
                    for item in assignment_remote
                ],
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                local_target,
                [f"{target_table}.{item}" for item in remote_target],
                ondelete="RESTRICT",
            ),
        )
        op.create_index(
            f"ix_{table}_target", table, ["company_id", target_column, "assignment_id"]
        )

    op.execute(
        "CREATE FUNCTION marketing_reject_append_only_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Marketing evidence is append-only'; END; $$"
    )
    for table in (
        "marketing_touches",
        "marketing_provider_snapshots",
        "marketing_attribution_assignments",
    ):
        op.execute(
            f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION marketing_reject_append_only_mutation()"
        )


def downgrade() -> None:
    for table in (
        "marketing_attribution_assignments",
        "marketing_provider_snapshots",
        "marketing_touches",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only ON {table}")
    op.execute("DROP FUNCTION IF EXISTS marketing_reject_append_only_mutation()")
    for table in (
        "marketing_job_attributions",
        "marketing_appointment_attributions",
        "marketing_lead_attributions",
        "marketing_customer_attributions",
    ):
        op.drop_table(table)
    op.drop_table("marketing_attribution_assignments")
    op.drop_table("marketing_touches")
    op.drop_table("marketing_provider_snapshots")
    op.drop_table("marketing_provider_sync_runs")
    op.drop_table("marketing_landing_pages")
    op.drop_table("marketing_campaigns")
    op.drop_table("marketing_provider_object_identities")
    op.drop_table("marketing_provider_accounts")
    op.drop_table("marketing_sources")
    op.drop_table("marketing_channels")
