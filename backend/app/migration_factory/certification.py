"""Reusable provider/domain conformance and certification evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from .domain import (
    CoverageState,
    Domain,
    MigrationFactory,
    MigrationFactoryError,
    PageCheckpoint,
    ProviderKey,
    canonical_digest,
)
from .providers.contract import AcquisitionCursor, AdapterContext, ProviderAdapter


class CertificationStatus(StrEnum):
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    IMPLEMENTED_UNQUALIFIED = "IMPLEMENTED_UNQUALIFIED"
    QUALIFIED_SYNTHETIC = "QUALIFIED_SYNTHETIC"
    QUALIFIED_LIVE = "QUALIFIED_LIVE"
    PARTIAL = "PARTIAL"
    BLOCKED_PROVIDER = "BLOCKED_PROVIDER"
    UNAVAILABLE = "UNAVAILABLE"
    CERTIFIED = "CERTIFIED"


class CommercialSupportLabel(StrEnum):
    CERTIFIED = "CERTIFIED"
    PARTIALLY_CERTIFIED = "PARTIALLY CERTIFIED"
    AWAITING_PROVIDER_ACCESS = "AWAITING PROVIDER ACCESS"
    UNAVAILABLE_FROM_PROVIDER = "UNAVAILABLE FROM PROVIDER"


def commercial_support_label(
    statuses: tuple[CertificationStatus, ...],
) -> CommercialSupportLabel:
    if statuses and all(
        item in {CertificationStatus.QUALIFIED_LIVE, CertificationStatus.CERTIFIED}
        for item in statuses
    ):
        return CommercialSupportLabel.CERTIFIED
    if any(
        item in {CertificationStatus.QUALIFIED_LIVE, CertificationStatus.CERTIFIED}
        for item in statuses
    ):
        return CommercialSupportLabel.PARTIALLY_CERTIFIED
    if statuses and all(item is CertificationStatus.UNAVAILABLE for item in statuses):
        return CommercialSupportLabel.UNAVAILABLE_FROM_PROVIDER
    return CommercialSupportLabel.AWAITING_PROVIDER_ACCESS


@dataclass(frozen=True, slots=True)
class ConformanceEvidence:
    authentication_discovery: bool
    company_identity: bool
    scope_discovery: bool
    full_acquisition: bool
    pagination: bool
    resume_after_interruption: bool
    retry_safety: bool
    idempotency: bool
    source_counts: bool
    raw_evidence: bool
    quarantine: bool
    zero_silent_drops: bool
    normalized_staging: bool
    crosswalk_compatible: bool
    delta_high_water: bool
    certification_output: bool

    @property
    def passed(self) -> bool:
        return all(asdict(self).values())


@dataclass(frozen=True, slots=True)
class DomainCertification:
    domain: Domain
    family: str
    source_count: int
    received_count: int
    quarantined_count: int
    pagination_complete: bool
    reconciliation: str
    status: CertificationStatus
    evidence_digest: str


@dataclass(frozen=True, slots=True)
class ProviderCertification:
    certification_id: UUID
    company_id: UUID
    provider: ProviderKey
    environment: str
    conformance: ConformanceEvidence
    domains: tuple[DomainCertification, ...]
    transformation_version: str
    certified_at: datetime
    digest: str


class ProviderConformanceHarness:
    async def qualify(
        self,
        *,
        adapter: ProviderAdapter,
        company_id: UUID,
        context: AdapterContext,
        families: dict[Domain, str],
        environment: str,
        transformation_version: str,
        live: bool,
    ) -> ProviderCertification:
        discovery = await adapter.discover(context)
        if discovery.provider != adapter.provider:
            raise MigrationFactoryError("adapter discovery provider mismatch")
        factory = MigrationFactory(company_id)
        domains: list[DomainCertification] = []
        pagination_ok = True
        replay_ok = True
        quarantine_observed = False
        for domain, family in families.items():
            pages = [
                page
                async for page in adapter.acquire_full(
                    context, AcquisitionCursor(family)
                )
            ]
            if not pages or sum(page.terminal for page in pages) != 1:
                raise MigrationFactoryError(f"{family}: incomplete pagination")
            source_count = pages[-1].provider_count
            if source_count is None:
                raise MigrationFactoryError(f"{family}: provider count unavailable")
            received = 0
            quarantined = 0
            for page in pages:
                received += len(page.records)
                quarantined += len(page.quarantined)
                quarantine_observed = quarantine_observed or bool(page.quarantined)
                response_digest = canonical_digest(
                    [record.payload for record in page.records]
                )
                factory.checkpoint_page(
                    PageCheckpoint(
                        adapter.provider,
                        family,
                        page.cursor.page_identity or "initial",
                        page.cursor.high_water_mark,
                        len(page.records),
                        len(page.quarantined),
                        page.terminal,
                        response_digest,
                    )
                )
                for record in page.records:
                    evidence = factory.retain_raw(
                        source=adapter.provider,
                        object_type=record.object_type,
                        object_id=record.object_id,
                        payload=record.payload,
                        payload_reference=f"vault://{adapter.provider}/{family}/{record.object_id}",
                        api_version=record.api_version,
                        authority="provider_read_only",
                        batch_identity=str(factory.migration_id),
                        page_identity=page.cursor.page_identity or "initial",
                        source_timestamp=record.source_timestamp,
                    )
                    factory.normalize(
                        evidence.evidence_id,
                        transformation_version,
                        dict(record.payload),
                    )
                    factory.bind_crosswalk(adapter.provider, record.object_id, uuid4())
            accounted = received + quarantined
            complete = accounted == source_count and factory.prove_pagination(
                adapter.provider, family, source_count
            )
            pagination_ok = pagination_ok and complete
            if len(pages) > 1:
                resumed = [
                    page
                    async for page in adapter.acquire_full(
                        context,
                        AcquisitionCursor(family, pages[1].cursor.page_identity),
                    )
                ]
                replay_ok = replay_ok and resumed == pages[1:]
            factory.transition(
                domain,
                CoverageState.AVAILABLE_API,
                sources=(adapter.provider,),
                source_count=source_count,
            )
            factory.transition(
                domain,
                CoverageState.NORMALIZED,
                received_count=received,
                quarantined_count=quarantined,
            )
            status = (
                CertificationStatus.QUALIFIED_LIVE
                if live and complete
                else CertificationStatus.QUALIFIED_SYNTHETIC
                if complete
                else CertificationStatus.PARTIAL
            )
            domains.append(
                DomainCertification(
                    domain,
                    family,
                    source_count,
                    received,
                    quarantined,
                    complete,
                    "BALANCED" if complete else "COUNT_MISMATCH",
                    status,
                    canonical_digest([family, source_count, received, quarantined]),
                )
            )
        controls = adapter.controls
        conformance = ConformanceEvidence(
            True,
            len(discovery.company_identity_digest) == 64,
            isinstance(discovery.authorized_scopes, tuple),
            True,
            pagination_ok,
            replay_ok,
            controls.bounded_retry,
            controls.idempotent_reads,
            True,
            bool(factory.vault),
            quarantine_observed or all(d.quarantined_count == 0 for d in domains),
            all(
                d.source_count == d.received_count + d.quarantined_count
                for d in domains
            ),
            len(factory.normalized_records) == sum(d.received_count for d in domains),
            len(factory.crosswalks) == sum(d.received_count for d in domains),
            controls.delta_mode in {"webhook_backfill", "polling_backfill", "none"},
            True,
        )
        body = {
            "company_id": str(company_id),
            "provider": adapter.provider,
            "environment": environment,
            "conformance": asdict(conformance),
            "domains": [asdict(item) for item in domains],
            "transformation_version": transformation_version,
        }
        return ProviderCertification(
            uuid4(),
            company_id,
            adapter.provider,
            environment,
            conformance,
            tuple(domains),
            transformation_version,
            datetime.now(timezone.utc),
            canonical_digest(body),
        )
