from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class AttributionRole(StrEnum):
    FIRST_TOUCH = "first_touch"
    LATEST_TOUCH = "latest_touch"
    BOOKING = "booking"
    JOB_ASSOCIATED = "job_associated"


class AttributionMethod(StrEnum):
    OBSERVED = "observed"
    PROVIDER_REPORTED = "provider_reported"
    MANUALLY_CONFIRMED = "manually_confirmed"
    LEGACY_IMPORT = "legacy_import"


class AttributionResolution(StrEnum):
    RESOLVED = "resolved"
    UNKNOWN = "unknown"
    CONFLICTING = "conflicting"
    NOT_AVAILABLE = "not_available"


class AttributionTargetType(StrEnum):
    CUSTOMER = "customer"
    LEAD = "lead"
    APPOINTMENT = "appointment"
    JOB = "job"


class MetricAvailability(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, slots=True)
class ProviderSnapshotEnvelope:
    object_type: str
    external_object_id: str
    provider_as_of: datetime
    observed_at: datetime
    schema_version: str
    normalized_payload: dict[str, object]
    payload_digest: str


class ReadOnlyMarketingProviderAdapter(Protocol):
    """Read-only adapter seam. Mutation methods are deliberately absent."""

    provider_family: str
    adapter_version: str

    async def snapshots(
        self,
        *,
        external_account_id: str,
        start_at: datetime | None,
        end_at: datetime | None,
    ) -> tuple[ProviderSnapshotEnvelope, ...]: ...


@dataclass(frozen=True, slots=True)
class MarketingOutcomeProjectionRequest:
    company_id: UUID
    branch_id: UUID | None
    interval_start: datetime
    interval_end: datetime
    as_of: datetime
    attribution_policy_version: str


@dataclass(frozen=True, slots=True)
class MarketingOutcomeCoverage:
    evidence_count: int
    coverage_percent: int
    missing_components: tuple[str, ...]
    availability: MetricAvailability


@dataclass(frozen=True, slots=True)
class MarketingOutcomeProjection:
    request: MarketingOutcomeProjectionRequest
    source_id: UUID | None
    campaign_id: UUID | None
    lead_ids: tuple[UUID, ...]
    appointment_ids: tuple[UUID, ...]
    job_ids: tuple[UUID, ...]
    estimate_proposal_ids: tuple[UUID, ...]
    invoice_ids: tuple[UUID, ...]
    payment_ids: tuple[UUID, ...]
    admitted_economics_result_ids: tuple[UUID, ...]
    coverage: MarketingOutcomeCoverage
