from datetime import datetime, timedelta, timezone

from app.marketing.provider_service import (
    marketing_spend_availability,
    owner_readiness_state,
)
from app.marketing.router import router
from app.marketing.schemas import MarketingReadinessProjection

NOW = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)


def state(**overrides: object) -> str:
    values = {
        "configuration_blocked": False,
        "connected": True,
        "account_bound": True,
        "ingestion_enabled": True,
        "last_successful_sync_at": NOW,
        "provider_error": False,
        "unresolved_findings": 0,
    }
    values.update(overrides)
    return owner_readiness_state(**values)  # type: ignore[arg-type]


def test_owner_states_identify_exact_next_control() -> None:
    assert state(configuration_blocked=True) == "CONFIGURATION_REQUIRED"
    assert state(connected=False) == "READY_TO_AUTHORIZE"
    assert state(account_bound=False) == "AUTHORIZED_ACCOUNT_SELECTION_REQUIRED"
    assert state(ingestion_enabled=False) == "CONNECTED_NOT_INGESTING"
    assert state(last_successful_sync_at=None) == "CONNECTED_NOT_INGESTING"
    assert state(provider_error=True) == "DEGRADED"
    assert state(unresolved_findings=1) == "DEGRADED"
    assert state() == "INGESTING"


def test_spend_availability_preserves_missing_partial_and_stale() -> None:
    assert (
        marketing_spend_availability(
            spend_count=0, performance_count=3, evidence_as_of=NOW, evaluated_at=NOW
        )
        == "UNAVAILABLE"
    )
    assert (
        marketing_spend_availability(
            spend_count=2, performance_count=3, evidence_as_of=NOW, evaluated_at=NOW
        )
        == "PARTIAL"
    )
    assert (
        marketing_spend_availability(
            spend_count=3,
            performance_count=3,
            evidence_as_of=NOW - timedelta(hours=73),
            evaluated_at=NOW,
        )
        == "STALE"
    )
    assert (
        marketing_spend_availability(
            spend_count=3, performance_count=3, evidence_as_of=NOW, evaluated_at=NOW
        )
        == "AVAILABLE"
    )


def test_projection_is_secret_safe_and_read_only() -> None:
    fields = set(MarketingReadinessProjection.model_fields)
    prohibited = {
        "token",
        "client_secret",
        "developer_token",
        "secret_reference",
        "credential_reference",
    }
    assert fields.isdisjoint(prohibited)
    readiness_routes = {
        method
        for route in router.routes
        if getattr(route, "path", None) == "/api/v1/marketing/readiness"
        for method in getattr(route, "methods", ()) or ()
    }
    assert readiness_routes == {"GET"}
