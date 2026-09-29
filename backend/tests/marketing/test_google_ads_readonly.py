from datetime import datetime, timezone
from inspect import getmembers, getsource, ismethod
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from app.marketing.google_ads import (
    GOOGLE_ADS_SCOPE,
    DiscoveredGoogleAdsAccount,
    FixtureGoogleAdsAdapter,
    GoogleAdsHttpAdapter,
    cursor_may_advance,
    digest_sensitive_text,
    minimize_landing_url,
)
from app.marketing.models import (
    MarketingPerformanceObservation,
    MarketingProviderAccountBinding,
    MarketingSearchTermObservation,
)
from app.marketing.provider_service import MarketingProviderService
from app.marketing.router import router
from app.marketing.secret_custody import (
    GoogleAdsCredentialEnvelope,
    require_environment_scoped_reference,
)
from app.platform.launch_controls import LAUNCH_ROLE_MATRIX, LaunchRoleCode
from app.platform.permissions.codes import MarketingPermission
from app.platform.provider_connections.models import ProviderConnectionBinding

NOW = datetime(2026, 9, 29, tzinfo=timezone.utc)


def test_google_ads_adapter_surface_is_read_only() -> None:
    adapter = FixtureGoogleAdsAdapter()
    public = {
        name
        for name, value in getmembers(adapter, predicate=ismethod)
        if not name.startswith("_")
    }
    assert public == {
        "discover_accounts",
        "campaign_performance",
        "search_term_performance",
    }
    prohibited = {"mutate", "execute", "campaign", "budget", "bid", "keyword"}
    assert not (public & prohibited)


@pytest.mark.asyncio
async def test_live_google_adapter_is_disabled_by_default() -> None:
    credentials = GoogleAdsCredentialEnvelope(
        "redacted", "redacted", "redacted", NOW, 1
    )
    async with httpx.AsyncClient() as client:
        with pytest.raises(RuntimeError, match="google_ads_live_access_disabled"):
            GoogleAdsHttpAdapter(client=client, credentials=credentials)


def test_routes_expose_no_google_provider_mutation_except_owner_binding() -> None:
    mutations = {
        (method, route.path)
        for route in router.routes
        for method in getattr(route, "methods", set())
        if "google-ads" in route.path and method not in {"GET", "HEAD", "OPTIONS"}
    }
    assert mutations == {("POST", "/api/v1/marketing/google-ads/account-bindings")}
    assert not any(
        f"/{word}" in path
        for _, path in mutations
        for word in ("campaigns", "budgets", "bids", "keywords", "targeting")
    )


def test_connection_metadata_excludes_secret_material() -> None:
    columns = {column.name for column in ProviderConnectionBinding.__table__.columns}
    assert (
        not {"client_secret", "refresh_token", "access_token", "developer_token"}
        & columns
    )
    assert {"client_credential_reference", "account_token_reference"} <= columns


def test_credential_references_are_environment_scoped() -> None:
    assert (
        require_environment_scoped_reference("marketing/beta/google-ads/token", "beta")
        == "marketing/beta/google-ads/token"
    )
    with pytest.raises(ValueError):
        require_environment_scoped_reference(
            "marketing/production/google-ads/token", "beta"
        )


@pytest.mark.asyncio
async def test_account_discovery_is_fixture_backed_and_does_not_bind() -> None:
    account = DiscoveredGoogleAdsAccount(
        "1234567890", "Redacted Plumbing", "USD", "America/New_York", False
    )
    adapter = FixtureGoogleAdsAdapter(accounts=(account,))
    assert await adapter.discover_accounts() == (account,)
    assert MarketingProviderAccountBinding.__table__.name not in repr(account)


def test_cursor_advances_only_after_committed_success() -> None:
    assert cursor_may_advance(partition_status="completed", committed=True)
    assert cursor_may_advance(
        partition_status="completed_with_exceptions", committed=True
    )
    assert not cursor_may_advance(partition_status="completed", committed=False)
    assert not cursor_may_advance(partition_status="failed", committed=True)


def test_owner_binding_duplicate_replay_conflicts_on_canonical_identity() -> None:
    unique_names = {
        constraint.name
        for constraint in MarketingProviderAccountBinding.__table__.constraints
    }
    assert "uq_marketing_provider_account_binding" in unique_names


def test_performance_preserves_null_distinct_from_zero() -> None:
    unavailable = MarketingPerformanceObservation(
        id=uuid4(), cost_micros=None, clicks=None, impressions=None
    )
    observed_zero = MarketingPerformanceObservation(
        id=uuid4(), cost_micros=0, clicks=0, impressions=0
    )
    assert unavailable.cost_micros is None
    assert observed_zero.cost_micros == 0


def test_search_terms_are_minimized_to_digests() -> None:
    assert "search_term_digest" in MarketingSearchTermObservation.__table__.c
    assert "search_term" not in MarketingSearchTermObservation.__table__.c
    assert len(digest_sensitive_text("emergency plumber near me")) == 64


def test_landing_url_minimization_removes_query_and_fragment() -> None:
    assert (
        minimize_landing_url(
            "HTTPS://Example.COM/service?gclid=secret&utm_source=x#frag"
        )
        == "https://example.com/service"
    )
    with pytest.raises(ValueError):
        minimize_landing_url("javascript:alert(1)")


def test_provider_reported_conversions_are_not_jobs_or_economics() -> None:
    columns = MarketingPerformanceObservation.__table__.c
    assert "provider_conversions" in columns
    assert "job_id" not in columns
    assert "revenue" not in columns
    assert "economic_contribution" not in columns


def test_field_technician_has_no_marketing_permissions() -> None:
    technician = next(
        role for role in LAUNCH_ROLE_MATRIX if role.code is LaunchRoleCode.TECHNICIAN
    )
    assert technician.permission_codes.isdisjoint(MarketingPermission.ALL)


def test_provider_reads_apply_company_and_branch_scope() -> None:
    source = getsource(MarketingProviderService)
    assert "context.company.id" in source
    assert "context.authorized_branch_ids" in source


def test_google_ads_scope_is_explicitly_broad() -> None:
    assert GOOGLE_ADS_SCOPE == "https://www.googleapis.com/auth/adwords"


def test_migration_lineage_and_append_only_contract() -> None:
    migration = Path(
        "alembic/versions/rg7c9e1f3i5k7_google_ads_readonly_ingestion.py"
    ).read_text()
    assert 'down_revision: str | Sequence[str] | None = "q7s9u1w3y5a7"' in migration
    for table in (
        "marketing_performance_observations",
        "marketing_search_term_observations",
        "marketing_provider_coverage_manifests",
    ):
        assert table in migration
    assert "marketing_reject_append_only_mutation" in migration


def test_no_live_google_client_dependency_or_endpoint() -> None:
    requirements = Path("requirements.txt").read_text().lower()
    assert "google-ads" not in requirements
    assert not any("oauth" in route.path for route in router.routes)
