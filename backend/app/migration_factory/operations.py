"""Stable owner and migration-specialist projections plus capacity model."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .certification import CertificationStatus, ProviderCertification


class OwnerMigrationState(StrEnum):
    CONNECT = "CONNECT"
    IMPORTING = "IMPORTING"
    REVIEW_NEEDED = "REVIEW_NEEDED"
    READY = "READY"
    COMPLETE = "COMPLETE"
    PROVIDER_ACTION_NEEDED = "PROVIDER_ACTION_NEEDED"


@dataclass(frozen=True, slots=True)
class OwnerDomainProgress:
    label: str
    state: str
    action_required: bool


@dataclass(frozen=True, slots=True)
class OwnerOnboardingStatus:
    migration_id: str
    state: OwnerMigrationState
    connected_providers: tuple[str, ...]
    progress: tuple[OwnerDomainProgress, ...]
    exception_count: int
    next_action: str | None
    ready_for_cutover: bool


@dataclass(frozen=True, slots=True)
class StaffDomainStatus:
    domain: str
    provider: str
    certification: str
    source_count: int
    received_count: int
    quarantine_count: int
    reconciliation: str


@dataclass(frozen=True, slots=True)
class StaffMigrationStatus:
    company_id: str
    migration_id: str
    providers: tuple[str, ...]
    domains: tuple[StaffDomainStatus, ...]
    errors: tuple[str, ...]
    conflict_count: int
    retry_count: int
    customer_actions: tuple[str, ...]
    certification_ready: bool


def owner_projection(
    migration_id: str, certificates: tuple[ProviderCertification, ...]
) -> OwnerOnboardingStatus:
    domains = tuple(item for cert in certificates for item in cert.domains)
    ready = bool(domains) and all(
        item.status
        in {CertificationStatus.QUALIFIED_LIVE, CertificationStatus.CERTIFIED}
        for item in domains
    )
    return OwnerOnboardingStatus(
        migration_id,
        OwnerMigrationState.READY if ready else OwnerMigrationState.REVIEW_NEEDED,
        tuple(sorted(str(cert.provider) for cert in certificates)),
        tuple(
            OwnerDomainProgress(
                item.domain.value.replace("_", " ").title(),
                "Ready"
                if item.status
                in {CertificationStatus.QUALIFIED_LIVE, CertificationStatus.CERTIFIED}
                else "Needs review",
                item.status
                in {CertificationStatus.PARTIAL, CertificationStatus.BLOCKED_PROVIDER},
            )
            for item in domains
        ),
        sum(item.status is CertificationStatus.PARTIAL for item in domains),
        None if ready else "Review the listed exceptions",
        ready,
    )


def staff_projection(
    migration_id: str,
    certificates: tuple[ProviderCertification, ...],
    *,
    errors: tuple[str, ...] = (),
    conflict_count: int = 0,
    retry_count: int = 0,
    customer_actions: tuple[str, ...] = (),
) -> StaffMigrationStatus:
    company_ids = {str(item.company_id) for item in certificates}
    if len(company_ids) != 1:
        raise ValueError("operations view requires exactly one company")
    domains = tuple(item for cert in certificates for item in cert.domains)
    return StaffMigrationStatus(
        company_ids.pop(),
        migration_id,
        tuple(sorted(str(cert.provider) for cert in certificates)),
        tuple(
            StaffDomainStatus(
                item.domain.value,
                str(cert.provider),
                item.status.value,
                item.source_count,
                item.received_count,
                item.quarantined_count,
                item.reconciliation,
            )
            for cert in certificates
            for item in cert.domains
        ),
        errors,
        conflict_count,
        retry_count,
        customer_actions,
        not errors
        and not customer_actions
        and all(item.pagination_complete for item in domains),
    )


@dataclass(frozen=True, slots=True)
class MonthlyCapacityModel:
    migrations_per_month: int = 200
    active_days_per_month: int = 20
    peak_start_multiplier: int = 3
    workers_per_provider_pool: int = 4
    exception_assumption_percent: int = 10

    @property
    def average_starts_per_day(self) -> int:
        return self.migrations_per_month // self.active_days_per_month

    @property
    def peak_start_capacity(self) -> int:
        return self.average_starts_per_day * self.peak_start_multiplier

    def verify(self) -> None:
        if self.peak_start_capacity < self.average_starts_per_day:
            raise ValueError("peak capacity is insufficient")
        if self.workers_per_provider_pool < 1:
            raise ValueError("provider worker pool is required")


CAPACITY_POLICY = {
    "queue": "tenant-fair provider/domain work items with per-tenant serialization",
    "retry": "bounded exponential backoff with jitter; permanent errors to exception queue",
    "throttling": "provider-specific token bucket configured only from verified limits",
    "metering": "calls, response bytes, retries, throttles, latency, and cost by tenant/provider/run",
    "failure_handling": "staff sees exact failed family/checkpoint and owner sees only actionable next step",
    "exception_assumption": "capacity reserve assumes 10%; replace with observed rolling rate",
}
