from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit

import httpx

from .secret_custody import GoogleAdsCredentialEnvelope

GOOGLE_ADS_PROVIDER = "google_ads"
GOOGLE_ADS_SCOPE = "https://www.googleapis.com/auth/adwords"


@dataclass(frozen=True, slots=True)
class DiscoveredGoogleAdsAccount:
    customer_id: str
    descriptive_name: str
    currency_code: str | None
    time_zone: str | None
    is_manager: bool


@dataclass(frozen=True, slots=True)
class GoogleAdsReportPartition:
    customer_id: str
    interval_start: datetime
    interval_end: datetime
    rows: tuple[dict[str, object], ...]
    provider_as_of: datetime
    api_version: str


class ReadOnlyGoogleAdsAdapter(Protocol):
    """Narrow reporting port. It intentionally cannot execute arbitrary GAQL."""

    adapter_version: str

    async def discover_accounts(self) -> tuple[DiscoveredGoogleAdsAccount, ...]: ...

    async def campaign_performance(
        self, *, customer_id: str, start_at: datetime, end_at: datetime
    ) -> GoogleAdsReportPartition: ...

    async def search_term_performance(
        self, *, customer_id: str, start_at: datetime, end_at: datetime
    ) -> GoogleAdsReportPartition: ...


class FixtureGoogleAdsAdapter:
    adapter_version = "fixture-v1"

    def __init__(
        self,
        *,
        accounts: tuple[DiscoveredGoogleAdsAccount, ...] = (),
        campaign_partitions: tuple[GoogleAdsReportPartition, ...] = (),
        search_partitions: tuple[GoogleAdsReportPartition, ...] = (),
    ) -> None:
        self._accounts = accounts
        self._campaigns = campaign_partitions
        self._search = search_partitions

    async def discover_accounts(self) -> tuple[DiscoveredGoogleAdsAccount, ...]:
        return self._accounts

    async def campaign_performance(
        self, *, customer_id: str, start_at: datetime, end_at: datetime
    ) -> GoogleAdsReportPartition:
        return _fixture_partition(self._campaigns, customer_id, start_at, end_at)

    async def search_term_performance(
        self, *, customer_id: str, start_at: datetime, end_at: datetime
    ) -> GoogleAdsReportPartition:
        return _fixture_partition(self._search, customer_id, start_at, end_at)


class GoogleAdsHttpAdapter:
    """Explicit REST reporting client. Construction fails unless live use is authorized."""

    adapter_version = "google-ads-rest-readonly-v1"
    api_version = "v22"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        credentials: GoogleAdsCredentialEnvelope,
        live_enabled: bool = False,
        login_customer_id: str | None = None,
    ) -> None:
        if not live_enabled:
            raise RuntimeError("google_ads_live_access_disabled")
        self._client = client
        self._credentials = credentials
        self._login_customer_id = login_customer_id

    async def discover_accounts(self) -> tuple[DiscoveredGoogleAdsAccount, ...]:
        response = await self._client.get(
            f"https://googleads.googleapis.com/{self.api_version}/customers:listAccessibleCustomers",
            headers=self._headers(),
        )
        response.raise_for_status()
        resources = response.json().get("resourceNames", [])
        return tuple(
            DiscoveredGoogleAdsAccount(
                customer_id=str(name).rsplit("/", 1)[-1],
                descriptive_name=f"Google Ads customer …{str(name)[-4:]}",
                currency_code=None,
                time_zone=None,
                is_manager=False,
            )
            for name in resources
        )

    async def campaign_performance(
        self, *, customer_id: str, start_at: datetime, end_at: datetime
    ) -> GoogleAdsReportPartition:
        query = (
            "SELECT campaign.id, campaign.name, campaign.status, "
            "campaign.advertising_channel_type, campaign.start_date, campaign.end_date, "
            "campaign.campaign_budget, metrics.cost_micros, metrics.impressions, "
            "metrics.clicks, metrics.interactions, metrics.phone_calls, metrics.conversions, "
            "metrics.conversions_value, segments.date, segments.device, "
            "segments.ad_network_type FROM campaign "
            f"WHERE segments.date BETWEEN '{start_at.date()}' AND '{end_at.date()}'"
        )
        rows = await self._report(customer_id, query)
        return GoogleAdsReportPartition(
            customer_id,
            start_at,
            end_at,
            rows,
            datetime.now(timezone.utc),
            self.api_version,
        )

    async def search_term_performance(
        self, *, customer_id: str, start_at: datetime, end_at: datetime
    ) -> GoogleAdsReportPartition:
        query = (
            "SELECT campaign.id, campaign.name, campaign_search_term_view.search_term, "
            "segments.keyword.info.text, segments.keyword.info.match_type, segments.date, "
            "segments.device, metrics.cost_micros, metrics.impressions, metrics.clicks, "
            "metrics.conversions, metrics.conversions_value FROM campaign_search_term_view "
            f"WHERE segments.date BETWEEN '{start_at.date()}' AND '{end_at.date()}'"
        )
        rows = await self._report(customer_id, query)
        return GoogleAdsReportPartition(
            customer_id,
            start_at,
            end_at,
            rows,
            datetime.now(timezone.utc),
            self.api_version,
        )

    async def _report(
        self, customer_id: str, query: str
    ) -> tuple[dict[str, object], ...]:
        response = await self._client.post(
            f"https://googleads.googleapis.com/{self.api_version}/customers/{customer_id}/googleAds:searchStream",
            headers=self._headers(),
            json={"query": query},
        )
        response.raise_for_status()
        rows: list[dict[str, object]] = []
        for batch in response.json():
            rows.extend(batch.get("results", []))
        return tuple(rows)

    def _headers(self) -> dict[str, str]:
        headers = {
            "authorization": f"Bearer {self._credentials.access_token}",
            "developer-token": self._credentials.developer_token,
        }
        if self._login_customer_id:
            headers["login-customer-id"] = self._login_customer_id
        return headers


def _fixture_partition(
    partitions: tuple[GoogleAdsReportPartition, ...],
    customer_id: str,
    start_at: datetime,
    end_at: datetime,
) -> GoogleAdsReportPartition:
    for partition in partitions:
        if (
            partition.customer_id == customer_id
            and partition.interval_start == start_at
            and partition.interval_end == end_at
        ):
            return partition
    raise LookupError("fixture_partition_not_found")


def minimize_landing_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("landing_url_invalid")
    host = parsed.hostname.encode("idna").decode("ascii").lower()
    port = parsed.port
    authority = host if port is None else f"{host}:{port}"
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme.lower(), authority, path, "", ""))


def digest_sensitive_text(value: str) -> str:
    return sha256(value.strip().encode("utf-8")).hexdigest()


def reread_start(watermark: datetime, *, adjustment_days: int = 30) -> datetime:
    if adjustment_days < 1 or adjustment_days > 90:
        raise ValueError("adjustment_window_out_of_bounds")
    return watermark - timedelta(days=adjustment_days)


def cursor_may_advance(*, partition_status: str, committed: bool) -> bool:
    return partition_status in {"completed", "completed_with_exceptions"} and committed
