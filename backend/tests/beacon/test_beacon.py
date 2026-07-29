from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.beacon.contracts import (
    BeaconCategory,
    BeaconEvidence,
    BeaconRankingFactorAvailability,
    BeaconSignalSource,
    BeaconSnapshot,
    OverdueAppointmentFacts,
    PastDueInvoiceFacts,
    PausedJobFacts,
)
from app.beacon.records import BeaconLifecycleEvent
from app.beacon.router import router
from app.beacon.service import BeaconQueryService, beacon_query_service
from app.database.session import get_database_session
from app.platform.permissions.authorization import (
    AuthorizationContext,
    PermissionDeniedError,
)
from app.platform.permissions.codes import AnalyticsPermission
from app.platform.permissions.dependencies import get_authorization_context

NOW = datetime(2026, 7, 28, 16, 0, tzinfo=timezone.utc)
COMPANY_ID = UUID("f47ac10b-58cc-4372-a567-0e02b2c3d479")


def context(*permissions: str) -> AuthorizationContext:
    value = object.__new__(AuthorizationContext)
    object.__setattr__(value, "company", SimpleNamespace(id=COMPANY_ID))
    object.__setattr__(value, "membership", SimpleNamespace(id=uuid4()))
    object.__setattr__(
        value,
        "effective_permissions",
        tuple(SimpleNamespace(code=permission) for permission in permissions),
    )
    return value


def evidence(entity_type: str) -> BeaconEvidence:
    return BeaconEvidence(
        entity_type=entity_type,
        entity_id=uuid4(),
        event_id=uuid4(),
        event_type=f"{entity_type}.updated",
        occurred_at=NOW - timedelta(hours=1),
    )


def snapshot(*, populated: bool = True) -> BeaconSnapshot:
    return BeaconSnapshot(
        company_id=COMPANY_ID,
        measured_at=NOW,
        overdue_appointments=OverdueAppointmentFacts(
            count=2 if populated else 0,
            earliest_window_start=NOW - timedelta(hours=25) if populated else None,
            evidence=(evidence("appointment"),) if populated else (),
        ),
        paused_jobs=PausedJobFacts(
            count=3 if populated else 0,
            earliest_paused_at=NOW - timedelta(hours=5) if populated else None,
            evidence=(evidence("job"),) if populated else (),
        ),
        past_due_invoices=PastDueInvoiceFacts(
            count=1 if populated else 0,
            total_amount=Decimal("125.50") if populated else Decimal(0),
            earliest_due_on=date(2026, 7, 18) if populated else None,
            evidence=(evidence("invoice"),) if populated else (),
        ),
    )


class FakeRepository:
    def __init__(self, value: BeaconSnapshot) -> None:
        self.value = value
        self.calls: list[tuple[UUID, datetime]] = []

    async def load_snapshot(
        self,
        _session: AsyncSession,
        *,
        company_id: UUID,
        measured_at: datetime,
    ) -> BeaconSnapshot:
        self.calls.append((company_id, measured_at))
        return self.value


class FakeLifecycleRepository:
    def __init__(self) -> None:
        self.events: dict[UUID, BeaconLifecycleEvent] = {}

    async def latest_for_conditions(
        self,
        _session: AsyncSession,
        *,
        company_id: UUID,
        condition_keys: tuple[UUID, ...],
    ) -> dict[UUID, BeaconLifecycleEvent]:
        assert company_id == COMPANY_ID
        return {key: self.events[key] for key in condition_keys if key in self.events}


def query_service(repository: FakeRepository) -> BeaconQueryService:
    return BeaconQueryService(
        repository,
        FakeLifecycleRepository(),  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_signals_are_immutable_deterministic_and_explainable() -> None:
    source = snapshot()
    repository = FakeRepository(source)
    service = query_service(repository)

    first = await service.list_signals(
        object(),  # type: ignore[arg-type]
        context=context(AnalyticsPermission.READ),
        now=NOW,
    )
    second = await service.list_signals(
        object(),  # type: ignore[arg-type]
        context=context(AnalyticsPermission.READ),
        now=NOW,
    )

    assert [item.id for item in first] == [item.id for item in second]
    assert [item.category for item in first] == [
        BeaconCategory.SCHEDULING,
        BeaconCategory.REVENUE,
        BeaconCategory.OPERATIONS,
    ]
    assert [item.priority.rank for item in first] == [1, 2, 3]
    assert [item.source for item in first] == [
        BeaconSignalSource.SCHEDULING,
        BeaconSignalSource.INVOICES,
        BeaconSignalSource.JOBS,
    ]
    assert [item.priority for item in first] == [item.priority for item in second]
    assert all(item.supporting_facts for item in first)
    assert all(item.recommended_action for item in first)
    assert all(item.expires_at == NOW + timedelta(minutes=15) for item in first)
    assert all(item.confidence.level == "high" for item in first)
    assert repository.calls == [(COMPANY_ID, NOW), (COMPANY_ID, NOW)]
    with pytest.raises(FrozenInstanceError):
        first[0].title = "Changed"  # type: ignore[misc]


@pytest.mark.asyncio
async def test_rule_factors_rank_revenue_jobs_and_appointments() -> None:
    service = query_service(FakeRepository(snapshot()))
    signals = await service.list_signals(
        object(),  # type: ignore[arg-type]
        context=context(AnalyticsPermission.READ),
        now=NOW,
    )
    by_source = {signal.source: signal for signal in signals}

    revenue = by_source[BeaconSignalSource.INVOICES]
    assert {
        factor.name: (factor.value, factor.contribution)
        for factor in revenue.priority.ranking_factors
    } == {
        "severity": ("important", 300),
        "affected_records": (1, 1),
        "condition_age": (10, 10),
        "financial_exposure": ("125.50", 0),
    }
    jobs = by_source[BeaconSignalSource.JOBS]
    assert {
        factor.name: factor.contribution for factor in jobs.priority.ranking_factors
    } == {
        "severity": 200,
        "affected_records": 3,
        "condition_age": 1,
        "financial_exposure": 0,
    }
    appointments = by_source[BeaconSignalSource.SCHEDULING]
    assert {
        factor.name: factor.contribution
        for factor in appointments.priority.ranking_factors
    } == {
        "severity": 400,
        "affected_records": 2,
        "condition_age": 6,
        "financial_exposure": 0,
    }
    assert all(signal.priority.explanation for signal in signals)


@pytest.mark.asyncio
async def test_missing_optional_factor_is_explicitly_not_applicable() -> None:
    service = query_service(FakeRepository(snapshot()))
    signals = await service.list_signals(
        object(),  # type: ignore[arg-type]
        context=context(AnalyticsPermission.READ),
        now=NOW,
    )
    jobs = next(signal for signal in signals if signal.source == "jobs")
    exposure = next(
        factor
        for factor in jobs.priority.ranking_factors
        if factor.name == "financial_exposure"
    )
    assert exposure.availability == BeaconRankingFactorAvailability.NOT_APPLICABLE
    assert exposure.value is None
    assert exposure.contribution == 0
    assert "not applicable" in exposure.explanation


@pytest.mark.asyncio
async def test_ties_resolve_by_stable_source_not_generation_order() -> None:
    tied = BeaconSnapshot(
        company_id=COMPANY_ID,
        measured_at=NOW,
        overdue_appointments=OverdueAppointmentFacts(
            count=1,
            earliest_window_start=NOW - timedelta(minutes=30),
            evidence=(evidence("appointment"),),
        ),
        paused_jobs=PausedJobFacts(
            count=1,
            earliest_paused_at=NOW - timedelta(minutes=30),
            evidence=(evidence("job"),),
        ),
        past_due_invoices=PastDueInvoiceFacts(
            count=0,
            total_amount=Decimal(0),
            earliest_due_on=None,
            evidence=(),
        ),
    )
    service = query_service(FakeRepository(tied))
    signals = await service.list_signals(
        object(),  # type: ignore[arg-type]
        context=context(AnalyticsPermission.READ),
        now=NOW,
    )

    assert [signal.priority.score for signal in signals] == [201, 201]
    assert [signal.source for signal in signals] == [
        BeaconSignalSource.JOBS,
        BeaconSignalSource.SCHEDULING,
    ]
    assert all("source" in signal.priority.tie_break_semantics for signal in signals)


@pytest.mark.asyncio
async def test_empty_authoritative_snapshot_produces_no_signal() -> None:
    service = query_service(FakeRepository(snapshot(populated=False)))
    assert (
        await service.list_signals(
            object(),  # type: ignore[arg-type]
            context=context(AnalyticsPermission.READ),
            now=NOW,
        )
        == ()
    )


@pytest.mark.asyncio
async def test_permission_and_company_scope_fail_closed() -> None:
    repository = FakeRepository(snapshot())
    service = query_service(repository)
    with pytest.raises(PermissionDeniedError):
        await service.list_signals(
            object(),  # type: ignore[arg-type]
            context=context(),
            now=NOW,
        )
    assert repository.calls == []


def test_category_architecture_is_complete() -> None:
    assert {item.value for item in BeaconCategory} == {
        "operations",
        "revenue",
        "customer",
        "scheduling",
        "workforce",
    }


@pytest.mark.asyncio
async def test_beacon_http_api_returns_bounded_company_scoped_signals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = FakeRepository(snapshot())
    lifecycle_repository = FakeLifecycleRepository()
    monkeypatch.setattr(beacon_query_service, "repository", repository)
    monkeypatch.setattr(
        beacon_query_service,
        "lifecycle_repository",
        lifecycle_repository,
    )
    app = FastAPI()
    app.include_router(router)

    async def session_override():
        yield object()

    async def context_override() -> AuthorizationContext:
        return context(AnalyticsPermission.READ)

    app.dependency_overrides[get_database_session] = session_override
    app.dependency_overrides[get_authorization_context] = context_override
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/beacon/signals")

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 3
    assert body["items"][0]["supporting_facts"]
    assert body["items"][0]["source"] == "scheduling"
    assert body["items"][0]["priority"]["rank"] == 1
    assert body["items"][0]["priority"]["ranking_factors"]
    assert body["items"][0]["expiration_policy"] == "replace_on_next_evaluation"
    assert body["snoozed_items"] == []
    assert body["lifecycle_commands_available"] is False
    assert "payload" not in str(body).lower()
