import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType

from .google_ads import (
    GoogleAdsReportPartition,
    digest_sensitive_text,
    minimize_landing_url,
)
from .models import (
    MarketingCampaign,
    MarketingLandingPage,
    MarketingPerformanceObservation,
    MarketingProviderAccount,
    MarketingProviderAccountBinding,
    MarketingProviderCoverageManifest,
    MarketingProviderCursor,
    MarketingProviderObjectIdentity,
    MarketingProviderReconciliationFinding,
    MarketingProviderSnapshot,
    MarketingProviderSyncRun,
    MarketingSearchTermObservation,
)


def _digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


class GoogleAdsIngestionError(ValueError):
    pass


class GoogleAdsIngestionService:
    """Admits already-fetched read-only report partitions atomically."""

    async def ingest_partition(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID,
        provider_account_id: UUID,
        source_id: UUID,
        stream: str,
        partition: GoogleAdsReportPartition,
        idempotency_key: str,
    ) -> MarketingProviderSyncRun:
        binding = await session.scalar(
            select(MarketingProviderAccountBinding).where(
                MarketingProviderAccountBinding.company_id == company_id,
                MarketingProviderAccountBinding.branch_id == branch_id,
                MarketingProviderAccountBinding.provider_account_id
                == provider_account_id,
                MarketingProviderAccountBinding.ingestion_enabled.is_(True),
            )
        )
        account = await session.scalar(
            select(MarketingProviderAccount).where(
                MarketingProviderAccount.company_id == company_id,
                MarketingProviderAccount.id == provider_account_id,
                MarketingProviderAccount.provider_family == "google_ads",
                MarketingProviderAccount.external_account_id == partition.customer_id,
            )
        )
        if binding is None or account is None:
            raise GoogleAdsIngestionError("google_ads_account_not_enabled")
        existing = await session.scalar(
            select(MarketingProviderSyncRun).where(
                MarketingProviderSyncRun.company_id == company_id,
                MarketingProviderSyncRun.provider_account_id == provider_account_id,
                MarketingProviderSyncRun.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            return existing
        run = MarketingProviderSyncRun(
            company_id=company_id,
            provider_account_id=provider_account_id,
            idempotency_key=idempotency_key,
            adapter_version="google-ads-readonly-v1",
            provider_api_version=partition.api_version,
            requested_start_at=partition.interval_start,
            requested_end_at=partition.interval_end,
            status="started",
            record_count=0,
            exception_count=0,
            started_at=datetime.now(timezone.utc),
        )
        session.add(run)
        await session.flush()
        missing: set[str] = set()
        for row in partition.rows:
            if stream == "campaign_performance":
                await self._campaign_row(
                    session,
                    run=run,
                    account=account,
                    branch_id=branch_id,
                    source_id=source_id,
                    partition=partition,
                    row=row,
                    missing=missing,
                )
            elif stream == "search_terms":
                await self._search_row(
                    session,
                    run=run,
                    account=account,
                    branch_id=branch_id,
                    partition=partition,
                    row=row,
                    missing=missing,
                )
            else:
                raise GoogleAdsIngestionError("google_ads_stream_unsupported")
        run.record_count = len(partition.rows)
        run.exception_count = len(missing)
        run.status = "completed_with_exceptions" if missing else "completed"
        run.completed_at = datetime.now(timezone.utc)
        cursor_payload = {
            "stream": stream,
            "customer_id": partition.customer_id,
            "watermark": partition.interval_end.isoformat(),
            "run_id": str(run.id),
        }
        cursor = await session.scalar(
            select(MarketingProviderCursor).where(
                MarketingProviderCursor.company_id == company_id,
                MarketingProviderCursor.provider_account_id == provider_account_id,
                MarketingProviderCursor.stream == stream,
                MarketingProviderCursor.partition_key == "daily",
            )
        )
        if cursor is None:
            cursor = MarketingProviderCursor(
                company_id=company_id,
                provider_account_id=provider_account_id,
                stream=stream,
                partition_key="daily",
                watermark_at=partition.interval_end,
                cursor_digest=_digest(cursor_payload),
                last_completed_sync_run_id=run.id,
                updated_at=datetime.now(timezone.utc),
            )
            session.add(cursor)
        elif partition.interval_end >= cursor.watermark_at:
            cursor.watermark_at = partition.interval_end
            cursor.cursor_digest = _digest(cursor_payload)
            cursor.last_completed_sync_run_id = run.id
            cursor.updated_at = datetime.now(timezone.utc)
        coverage_payload = {
            "run_id": str(run.id),
            "missing": sorted(missing),
            "count": len(partition.rows),
        }
        session.add(
            MarketingProviderCoverageManifest(
                company_id=company_id,
                branch_id=branch_id,
                provider_account_id=provider_account_id,
                sync_run_id=run.id,
                interval_start=partition.interval_start,
                interval_end=partition.interval_end,
                as_of=partition.provider_as_of,
                attribution_policy_version="marketing-attribution.v1",
                evidence_count=len(partition.rows),
                coverage_percent=100
                if not missing
                else 0
                if not partition.rows
                else 80,
                missing_components=sorted(missing),
                availability="complete" if not missing else "partial",
                manifest_digest=_digest(coverage_payload),
            )
        )
        for component in sorted(missing):
            session.add(
                MarketingProviderReconciliationFinding(
                    company_id=company_id,
                    branch_id=branch_id,
                    provider_account_id=provider_account_id,
                    sync_run_id=run.id,
                    kind="missing_or_withheld_evidence",
                    state="open",
                    missing_components=[component],
                    details={"stream": stream},
                    finding_digest=_digest(
                        {**coverage_payload, "component": component}
                    ),
                    observed_at=partition.provider_as_of,
                )
            )
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=EventType.MARKETING_PROVIDER_SYNC_COMPLETED,
                entity_type="marketing_provider_sync_run",
                entity_id=run.id,
                company_id=company_id,
                branch_id=branch_id,
                payload={
                    "version": "1.0",
                    "provider_family": "google_ads",
                    "stream": stream,
                    "record_count": len(partition.rows),
                    "exception_count": len(missing),
                    "idempotency_key": idempotency_key,
                },
            ),
        )
        await session.commit()
        await session.refresh(run)
        return run

    async def _campaign_row(
        self,
        session: AsyncSession,
        *,
        run: MarketingProviderSyncRun,
        account: MarketingProviderAccount,
        branch_id: UUID,
        source_id: UUID,
        partition: GoogleAdsReportPartition,
        row: dict[str, object],
        missing: set[str],
    ) -> None:
        campaign_id = str(row["campaign_id"])
        identity = await self._identity(
            session, run, account, "campaign", campaign_id, partition.provider_as_of
        )
        campaign = await session.scalar(
            select(MarketingCampaign).where(
                MarketingCampaign.company_id == run.company_id,
                MarketingCampaign.provider_object_identity_id == identity.id,
            )
        )
        if campaign is None:
            session.add(
                MarketingCampaign(
                    company_id=run.company_id,
                    source_id=source_id,
                    provider_object_identity_id=identity.id,
                    name=str(row.get("campaign_name") or "Google Ads campaign"),
                    state=_campaign_state(row.get("campaign_status")),
                )
            )
        final_url = row.get("final_url")
        minimized_url = minimize_landing_url(str(final_url)) if final_url else None
        if minimized_url:
            parsed_host_path = minimized_url.split("/", 3)
            landing = await session.scalar(
                select(MarketingLandingPage).where(
                    MarketingLandingPage.company_id == run.company_id,
                    MarketingLandingPage.normalized_url == minimized_url,
                )
            )
            if landing is None:
                session.add(
                    MarketingLandingPage(
                        company_id=run.company_id,
                        normalized_url=minimized_url,
                        host=parsed_host_path[2],
                        path="/" + parsed_host_path[3]
                        if len(parsed_host_path) > 3
                        else "/",
                        first_observed_at=partition.provider_as_of,
                        last_observed_at=partition.provider_as_of,
                    )
                )
        normalized = {
            key: value
            for key, value in row.items()
            if key not in {"search_term", "keyword_text", "final_url"}
        }
        normalized["minimized_final_url"] = minimized_url
        snapshot = MarketingProviderSnapshot(
            company_id=run.company_id,
            provider_account_id=account.id,
            sync_run_id=run.id,
            provider_object_identity_id=identity.id,
            object_type="campaign_performance",
            external_object_id=campaign_id,
            provider_as_of=partition.provider_as_of,
            observed_at=partition.provider_as_of,
            schema_version=partition.api_version,
            payload_digest=_digest(normalized),
            normalized_payload=normalized,
        )
        session.add(snapshot)
        await session.flush()
        metric_names = ("cost_micros", "impressions", "clicks", "interactions", "calls")
        for name in metric_names:
            if name not in row or row[name] is None:
                missing.add(name)
        payload = {
            "campaign": campaign_id,
            "interval": partition.interval_start.isoformat(),
            **normalized,
        }
        session.add(
            MarketingPerformanceObservation(
                company_id=run.company_id,
                branch_id=branch_id,
                provider_account_id=account.id,
                provider_object_identity_id=identity.id,
                provider_snapshot_id=snapshot.id,
                interval_start=partition.interval_start,
                interval_end=partition.interval_end,
                provider_as_of=partition.provider_as_of,
                grain="campaign_daily",
                dimensions=_mapping(row.get("dimensions")),
                currency=account.currency,
                cost_micros=_optional_int(row.get("cost_micros")),
                impressions=_optional_int(row.get("impressions")),
                clicks=_optional_int(row.get("clicks")),
                interactions=_optional_int(row.get("interactions")),
                calls=_optional_int(row.get("calls")),
                provider_conversions=_optional_decimal(row.get("conversions")),
                provider_conversion_value=_optional_decimal(
                    row.get("conversion_value")
                ),
                schema_version=partition.api_version,
                observation_digest=_digest(payload),
            )
        )

    async def _search_row(
        self,
        session: AsyncSession,
        *,
        run: MarketingProviderSyncRun,
        account: MarketingProviderAccount,
        branch_id: UUID,
        partition: GoogleAdsReportPartition,
        row: dict[str, object],
        missing: set[str],
    ) -> None:
        campaign_id = str(row["campaign_id"])
        identity = await self._identity(
            session, run, account, "campaign", campaign_id, partition.provider_as_of
        )
        search_term = row.get("search_term")
        if not isinstance(search_term, str) or not search_term.strip():
            missing.add("search_term_withheld")
            term_digest = digest_sensitive_text("withheld")
        else:
            term_digest = digest_sensitive_text(search_term)
        normalized = {
            k: v for k, v in row.items() if k not in {"search_term", "keyword_text"}
        }
        snapshot = MarketingProviderSnapshot(
            company_id=run.company_id,
            provider_account_id=account.id,
            sync_run_id=run.id,
            provider_object_identity_id=identity.id,
            object_type="search_term_performance",
            external_object_id=f"{campaign_id}:{term_digest}",
            provider_as_of=partition.provider_as_of,
            observed_at=partition.provider_as_of,
            schema_version=partition.api_version,
            payload_digest=_digest(normalized),
            normalized_payload=normalized,
        )
        session.add(snapshot)
        await session.flush()
        session.add(
            MarketingSearchTermObservation(
                company_id=run.company_id,
                branch_id=branch_id,
                provider_account_id=account.id,
                provider_snapshot_id=snapshot.id,
                campaign_identity_id=identity.id,
                interval_start=partition.interval_start,
                interval_end=partition.interval_end,
                provider_as_of=partition.provider_as_of,
                search_term_digest=term_digest,
                keyword_text_digest=(
                    digest_sensitive_text(str(row["keyword_text"]))
                    if row.get("keyword_text")
                    else None
                ),
                match_type=str(row["match_type"]) if row.get("match_type") else None,
                status=str(row["status"]) if row.get("status") else None,
                metrics=_mapping(row.get("metrics")),
                dimensions=_mapping(row.get("dimensions")),
                schema_version=partition.api_version,
                observation_digest=_digest(
                    {"campaign": campaign_id, "term": term_digest, **normalized}
                ),
            )
        )

    async def _identity(
        self,
        session: AsyncSession,
        run: MarketingProviderSyncRun,
        account: MarketingProviderAccount,
        object_type: str,
        external_id: str,
        observed_at: datetime,
    ) -> MarketingProviderObjectIdentity:
        identity = await session.scalar(
            select(MarketingProviderObjectIdentity).where(
                MarketingProviderObjectIdentity.company_id == run.company_id,
                MarketingProviderObjectIdentity.provider_account_id == account.id,
                MarketingProviderObjectIdentity.object_type == object_type,
                MarketingProviderObjectIdentity.external_object_id == external_id,
            )
        )
        if identity is None:
            identity = MarketingProviderObjectIdentity(
                company_id=run.company_id,
                provider_account_id=account.id,
                object_type=object_type,
                external_object_id=external_id,
                external_version=run.provider_api_version,
                first_observed_at=observed_at,
                last_observed_at=observed_at,
            )
            session.add(identity)
            await session.flush()
        elif observed_at > identity.last_observed_at:
            identity.last_observed_at = observed_at
        return identity


def _optional_int(value: object) -> int | None:
    return None if value is None else int(str(value))


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _campaign_state(value: object) -> str:
    return {
        "ENABLED": "active",
        "PAUSED": "paused",
        "REMOVED": "ended",
    }.get(str(value).upper(), "unknown")


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        return {}
    return value


google_ads_ingestion_service = GoogleAdsIngestionService()
