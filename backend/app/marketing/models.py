from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MarketingChannel(Base):
    __tablename__ = "marketing_channels"
    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_marketing_channels_code"),
        UniqueConstraint("company_id", "id", name="uq_marketing_channels_company_id"),
        CheckConstraint("length(btrim(code)) > 0", name="ck_marketing_channels_code"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class MarketingSource(Base):
    __tablename__ = "marketing_sources"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "channel_id"],
            ["marketing_channels.company_id", "marketing_channels.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("company_id", "code", name="uq_marketing_sources_code"),
        UniqueConstraint("company_id", "id", name="uq_marketing_sources_company_id"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    channel_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    provider_family: Mapped[str | None] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class MarketingProviderAccount(Base):
    __tablename__ = "marketing_provider_accounts"
    __table_args__ = (
        CheckConstraint(
            "state IN ('configured','active','paused','disconnected')",
            name="ck_marketing_provider_accounts_state",
        ),
        UniqueConstraint(
            "company_id",
            "provider_family",
            "external_account_id",
            name="uq_marketing_provider_accounts_external",
        ),
        UniqueConstraint(
            "company_id", "id", name="uq_marketing_provider_accounts_company_id"
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider_family: Mapped[str] = mapped_column(String(80), nullable=False)
    external_account_id: Mapped[str] = mapped_column(String(191), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="configured")
    timezone: Mapped[str | None] = mapped_column(String(100))
    currency: Mapped[str | None] = mapped_column(String(3))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class MarketingProviderObjectIdentity(Base):
    __tablename__ = "marketing_provider_object_identities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "provider_account_id"],
            [
                "marketing_provider_accounts.company_id",
                "marketing_provider_accounts.id",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "provider_account_id",
            "object_type",
            "external_object_id",
            name="uq_marketing_provider_objects_external",
        ),
        UniqueConstraint(
            "company_id", "id", name="uq_marketing_provider_objects_company_id"
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider_account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    object_type: Mapped[str] = mapped_column(String(80), nullable=False)
    external_object_id: Mapped[str] = mapped_column(String(191), nullable=False)
    external_version: Mapped[str | None] = mapped_column(String(100))
    first_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class MarketingCampaign(Base):
    __tablename__ = "marketing_campaigns"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "source_id"],
            ["marketing_sources.company_id", "marketing_sources.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "provider_object_identity_id"],
            [
                "marketing_provider_object_identities.company_id",
                "marketing_provider_object_identities.id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "state IN ('unknown','active','paused','ended')",
            name="ck_marketing_campaigns_state",
        ),
        UniqueConstraint(
            "company_id",
            "provider_object_identity_id",
            name="uq_marketing_campaigns_provider_object",
        ),
        UniqueConstraint("company_id", "id", name="uq_marketing_campaigns_company_id"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    provider_object_identity_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True)
    )
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="unknown")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class MarketingLandingPage(Base):
    __tablename__ = "marketing_landing_pages"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "normalized_url", name="uq_marketing_landing_pages_url"
        ),
        UniqueConstraint(
            "company_id", "id", name="uq_marketing_landing_pages_company_id"
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    normalized_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(String(1000), nullable=False)
    first_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class MarketingProviderSyncRun(Base):
    __tablename__ = "marketing_provider_sync_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "provider_account_id"],
            [
                "marketing_provider_accounts.company_id",
                "marketing_provider_accounts.id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('started','completed','completed_with_exceptions','failed')",
            name="ck_marketing_sync_runs_status",
        ),
        CheckConstraint(
            "record_count >= 0 AND exception_count >= 0",
            name="ck_marketing_sync_runs_counts",
        ),
        UniqueConstraint(
            "company_id",
            "provider_account_id",
            "idempotency_key",
            name="uq_marketing_sync_runs_idempotency",
        ),
        UniqueConstraint("company_id", "id", name="uq_marketing_sync_runs_company_id"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider_account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    adapter_version: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_api_version: Mapped[str | None] = mapped_column(String(100))
    requested_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cursor_digest: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    record_count: Mapped[int] = mapped_column(nullable=False, default=0)
    exception_count: Mapped[int] = mapped_column(nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MarketingProviderSnapshot(Base):
    __tablename__ = "marketing_provider_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "provider_account_id"],
            [
                "marketing_provider_accounts.company_id",
                "marketing_provider_accounts.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "sync_run_id"],
            [
                "marketing_provider_sync_runs.company_id",
                "marketing_provider_sync_runs.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "provider_object_identity_id"],
            [
                "marketing_provider_object_identities.company_id",
                "marketing_provider_object_identities.id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "length(payload_digest) = 64", name="ck_marketing_snapshots_digest"
        ),
        UniqueConstraint(
            "company_id",
            "provider_account_id",
            "object_type",
            "external_object_id",
            "provider_as_of",
            "schema_version",
            "payload_digest",
            name="uq_marketing_snapshots_revision",
        ),
        UniqueConstraint("company_id", "id", name="uq_marketing_snapshots_company_id"),
        Index(
            "ix_marketing_snapshots_object_as_of",
            "company_id",
            "provider_account_id",
            "object_type",
            "external_object_id",
            "provider_as_of",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider_account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    sync_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    provider_object_identity_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True)
    )
    object_type: Mapped[str] = mapped_column(String(80), nullable=False)
    external_object_id: Mapped[str] = mapped_column(String(191), nullable=False)
    provider_as_of: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    schema_version: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_payload: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class MarketingTouch(Base):
    __tablename__ = "marketing_touches"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "source_id"],
            ["marketing_sources.company_id", "marketing_sources.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "campaign_id"],
            ["marketing_campaigns.company_id", "marketing_campaigns.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "landing_page_id"],
            ["marketing_landing_pages.company_id", "marketing_landing_pages.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "provider_snapshot_id"],
            [
                "marketing_provider_snapshots.company_id",
                "marketing_provider_snapshots.id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "resolution IN ('resolved','unknown','conflicting','not_available')",
            name="ck_marketing_touches_resolution",
        ),
        CheckConstraint(
            "length(evidence_digest) = 64", name="ck_marketing_touches_digest"
        ),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_marketing_touches_idempotency"
        ),
        UniqueConstraint("company_id", "id", name="uq_marketing_touches_company_id"),
        Index(
            "ix_marketing_touches_observed",
            "company_id",
            "branch_id",
            "observed_at",
            "id",
        ),
        Index(
            "ix_marketing_touches_resolution", "company_id", "resolution", "observed_at"
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    branch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    source_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    campaign_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    landing_page_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    provider_snapshot_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    evidence_kind: Mapped[str] = mapped_column(String(80), nullable=False)
    resolution: Mapped[str] = mapped_column(String(24), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    utm_source: Mapped[str | None] = mapped_column(String(200))
    utm_medium: Mapped[str | None] = mapped_column(String(200))
    utm_campaign: Mapped[str | None] = mapped_column(String(240))
    referrer_origin: Mapped[str | None] = mapped_column(String(500))
    click_id_kind: Mapped[str | None] = mapped_column(String(40))
    click_id_digest: Mapped[str | None] = mapped_column(String(64))
    tracking_reference_digest: Mapped[str | None] = mapped_column(String(64))
    legacy_source_value: Mapped[str | None] = mapped_column(String(100))
    provenance: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)


class MarketingAttributionAssignment(Base):
    __tablename__ = "marketing_attribution_assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "touch_id"],
            ["marketing_touches.company_id", "marketing_touches.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "supersedes_assignment_id"],
            [
                "marketing_attribution_assignments.company_id",
                "marketing_attribution_assignments.id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "role IN ('first_touch','latest_touch','booking','job_associated')",
            name="ck_marketing_attribution_role",
        ),
        CheckConstraint(
            "method IN ('observed','provider_reported','manually_confirmed','legacy_import')",
            name="ck_marketing_attribution_method",
        ),
        CheckConstraint(
            "resolution IN ('resolved','unknown','conflicting','not_available')",
            name="ck_marketing_attribution_resolution",
        ),
        CheckConstraint(
            "method <> 'manually_confirmed' OR (actor_user_id IS NOT NULL AND length(btrim(reason)) > 0)",
            name="ck_marketing_attribution_manual_reason",
        ),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_marketing_attribution_idempotency"
        ),
        UniqueConstraint(
            "company_id", "id", name="uq_marketing_attribution_company_id"
        ),
        UniqueConstraint(
            "company_id",
            "branch_id",
            "id",
            name="uq_marketing_attribution_company_branch_id",
        ),
        Index(
            "ix_marketing_attribution_resolution",
            "company_id",
            "resolution",
            "assigned_at",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    branch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    touch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    role: Mapped[str] = mapped_column(String(24), nullable=False)
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    resolution: Mapped[str] = mapped_column(String(24), nullable=False)
    supporting_evidence_reference: Mapped[str] = mapped_column(
        String(300), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    supersedes_assignment_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class _AttributionLink:
    assignment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))


class MarketingCustomerAttribution(_AttributionLink, Base):
    __tablename__ = "marketing_customer_attributions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "assignment_id"],
            [
                "marketing_attribution_assignments.company_id",
                "marketing_attribution_assignments.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "customer_id"],
            ["customers.company_id", "customers.id"],
            ondelete="RESTRICT",
        ),
        Index(
            "ix_marketing_customer_attributions_target",
            "company_id",
            "customer_id",
            "assignment_id",
        ),
    )
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)


class MarketingLeadAttribution(_AttributionLink, Base):
    __tablename__ = "marketing_lead_attributions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id", "assignment_id"],
            [
                "marketing_attribution_assignments.company_id",
                "marketing_attribution_assignments.branch_id",
                "marketing_attribution_assignments.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id", "lead_id"],
            [
                "pipeline_leads.company_id",
                "pipeline_leads.branch_id",
                "pipeline_leads.id",
            ],
            ondelete="RESTRICT",
        ),
        Index(
            "ix_marketing_lead_attributions_target",
            "company_id",
            "lead_id",
            "assignment_id",
        ),
    )
    lead_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)


class MarketingAppointmentAttribution(_AttributionLink, Base):
    __tablename__ = "marketing_appointment_attributions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id", "assignment_id"],
            [
                "marketing_attribution_assignments.company_id",
                "marketing_attribution_assignments.branch_id",
                "marketing_attribution_assignments.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id", "appointment_id"],
            ["appointments.company_id", "appointments.branch_id", "appointments.id"],
            ondelete="RESTRICT",
        ),
        Index(
            "ix_marketing_appointment_attributions_target",
            "company_id",
            "appointment_id",
            "assignment_id",
        ),
    )
    appointment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)


class MarketingJobAttribution(_AttributionLink, Base):
    __tablename__ = "marketing_job_attributions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id", "assignment_id"],
            [
                "marketing_attribution_assignments.company_id",
                "marketing_attribution_assignments.branch_id",
                "marketing_attribution_assignments.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            ondelete="RESTRICT",
        ),
        Index(
            "ix_marketing_job_attributions_target",
            "company_id",
            "job_id",
            "assignment_id",
        ),
    )
    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)


class MarketingProviderAccountBinding(Base):
    __tablename__ = "marketing_provider_account_bindings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "provider_account_id"],
            [
                "marketing_provider_accounts.company_id",
                "marketing_provider_accounts.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "connection_binding_id"],
            [
                "platform_provider_connection_bindings.company_id",
                "platform_provider_connection_bindings.id",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "provider_account_id",
            "branch_id",
            name="uq_marketing_provider_account_binding",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    provider_account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    connection_binding_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    bound_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    ingestion_enabled: Mapped[bool] = mapped_column(nullable=False, default=False)
    bound_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class MarketingProviderCursor(Base):
    __tablename__ = "marketing_provider_cursors"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "provider_account_id"],
            [
                "marketing_provider_accounts.company_id",
                "marketing_provider_accounts.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "last_completed_sync_run_id"],
            [
                "marketing_provider_sync_runs.company_id",
                "marketing_provider_sync_runs.id",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "provider_account_id",
            "stream",
            "partition_key",
            name="uq_marketing_provider_cursor_partition",
        ),
        CheckConstraint(
            "length(cursor_digest) = 64", name="ck_marketing_cursor_digest"
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider_account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    stream: Mapped[str] = mapped_column(String(80), nullable=False)
    partition_key: Mapped[str] = mapped_column(String(160), nullable=False)
    watermark_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    cursor_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    last_completed_sync_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class MarketingPerformanceObservation(Base):
    __tablename__ = "marketing_performance_observations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "provider_account_id"],
            [
                "marketing_provider_accounts.company_id",
                "marketing_provider_accounts.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "provider_object_identity_id"],
            [
                "marketing_provider_object_identities.company_id",
                "marketing_provider_object_identities.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "provider_snapshot_id"],
            [
                "marketing_provider_snapshots.company_id",
                "marketing_provider_snapshots.id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "interval_end > interval_start", name="ck_marketing_performance_interval"
        ),
        CheckConstraint(
            "length(observation_digest) = 64", name="ck_marketing_performance_digest"
        ),
        UniqueConstraint(
            "company_id", "observation_digest", name="uq_marketing_performance_digest"
        ),
        Index(
            "ix_marketing_performance_interval",
            "company_id",
            "provider_account_id",
            "interval_start",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    branch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    provider_account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    provider_object_identity_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True)
    )
    provider_snapshot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    interval_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    interval_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    provider_as_of: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    grain: Mapped[str] = mapped_column(String(80), nullable=False)
    dimensions: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    currency: Mapped[str | None] = mapped_column(String(3))
    cost_micros: Mapped[int | None] = mapped_column(BigInteger)
    impressions: Mapped[int | None] = mapped_column(BigInteger)
    clicks: Mapped[int | None] = mapped_column(BigInteger)
    interactions: Mapped[int | None] = mapped_column(BigInteger)
    calls: Mapped[int | None] = mapped_column(BigInteger)
    provider_conversions: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    provider_conversion_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    observation_digest: Mapped[str] = mapped_column(String(64), nullable=False)


class MarketingSearchTermObservation(Base):
    __tablename__ = "marketing_search_term_observations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "provider_snapshot_id"],
            [
                "marketing_provider_snapshots.company_id",
                "marketing_provider_snapshots.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "provider_account_id"],
            [
                "marketing_provider_accounts.company_id",
                "marketing_provider_accounts.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "campaign_identity_id"],
            [
                "marketing_provider_object_identities.company_id",
                "marketing_provider_object_identities.id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "length(search_term_digest) = 64", name="ck_marketing_search_term_digest"
        ),
        CheckConstraint(
            "length(observation_digest) = 64",
            name="ck_marketing_search_observation_digest",
        ),
        UniqueConstraint(
            "company_id",
            "observation_digest",
            name="uq_marketing_search_observation_digest",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    branch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    provider_account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    provider_snapshot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    campaign_identity_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    interval_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    interval_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    provider_as_of: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    search_term_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    keyword_text_digest: Mapped[str | None] = mapped_column(String(64))
    match_type: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str | None] = mapped_column(String(40))
    metrics: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    dimensions: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    observation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class MarketingProviderReconciliationFinding(Base):
    __tablename__ = "marketing_provider_reconciliation_findings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "provider_account_id"],
            [
                "marketing_provider_accounts.company_id",
                "marketing_provider_accounts.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "sync_run_id"],
            [
                "marketing_provider_sync_runs.company_id",
                "marketing_provider_sync_runs.id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "state IN ('open','resolved','not_available','accepted_gap')",
            name="ck_marketing_reconciliation_state",
        ),
        UniqueConstraint(
            "company_id", "finding_digest", name="uq_marketing_reconciliation_digest"
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    branch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    provider_account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    sync_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    missing_components: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    details: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    finding_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class MarketingProviderCoverageManifest(Base):
    __tablename__ = "marketing_provider_coverage_manifests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "provider_account_id"],
            [
                "marketing_provider_accounts.company_id",
                "marketing_provider_accounts.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "sync_run_id"],
            [
                "marketing_provider_sync_runs.company_id",
                "marketing_provider_sync_runs.id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "availability IN ('complete','partial','unavailable','not_applicable')",
            name="ck_marketing_provider_coverage_availability",
        ),
        CheckConstraint(
            "coverage_percent BETWEEN 0 AND 100",
            name="ck_marketing_provider_coverage_percent",
        ),
        UniqueConstraint(
            "company_id",
            "manifest_digest",
            name="uq_marketing_provider_coverage_digest",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    branch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    provider_account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    sync_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    interval_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    interval_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attribution_policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    evidence_count: Mapped[int] = mapped_column(nullable=False)
    coverage_percent: Mapped[int] = mapped_column(nullable=False)
    missing_components: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    availability: Mapped[str] = mapped_column(String(24), nullable=False)
    manifest_digest: Mapped[str] = mapped_column(String(64), nullable=False)
