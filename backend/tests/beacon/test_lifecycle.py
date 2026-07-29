from contextlib import AbstractAsyncContextManager
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.beacon.contracts import BeaconLifecycleAction
from app.beacon.errors import (
    BeaconSignalNotFoundError,
    BeaconSignalStaleError,
    BeaconSnoozeInvalidError,
)
from app.beacon.lifecycle import (
    BeaconLifecycleService,
    RecordBeaconLifecycleAction,
)
from app.beacon.records import BeaconLifecycleEvent, BeaconSignal
from app.beacon.service import BeaconQueryService
from app.platform.permissions.authorization import (
    AuthorizationContext,
    PermissionDeniedError,
)
from app.platform.permissions.codes import AnalyticsPermission, BeaconPermission
from tests.beacon.test_beacon import (
    COMPANY_ID,
    NOW,
    FakeLifecycleRepository,
    FakeRepository,
    context,
    query_service,
    snapshot,
)


class Transaction(AbstractAsyncContextManager[None]):
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_args: object) -> None:
        return None


class FakeSession:
    def begin(self) -> Transaction:
        return Transaction()


class CurrentSignalQuery:
    def __init__(self, signal: BeaconSignal | None) -> None:
        self.signal = signal
        self.company_ids: list[UUID] = []

    async def evaluate_current(
        self,
        _session: AsyncSession,
        *,
        company_id: UUID,
        measured_at: datetime,
    ) -> tuple[BeaconSignal, ...]:
        assert measured_at == NOW
        self.company_ids.append(company_id)
        return (self.signal,) if self.signal else ()


class LifecycleRepository:
    def __init__(self) -> None:
        self.events: list[BeaconLifecycleEvent] = []
        self.history_company_ids: list[UUID] = []

    async def append(
        self, _session: AsyncSession, **values: object
    ) -> BeaconLifecycleEvent:
        event = BeaconLifecycleEvent(
            id=uuid4(),
            company_id=values["company_id"],  # type: ignore[arg-type]
            condition_key=values["condition_key"],  # type: ignore[arg-type]
            signal_id=values["signal_id"],  # type: ignore[arg-type]
            rule_code=values["rule_code"],  # type: ignore[arg-type]
            signal_source=values["signal_source"],  # type: ignore[arg-type]
            evidence_digest=values["evidence_digest"],  # type: ignore[arg-type]
            action=values["action"],  # type: ignore[arg-type]
            actor_membership_id=values["actor_membership_id"],  # type: ignore[arg-type]
            action_at=values["action_at"],  # type: ignore[arg-type]
            snooze_until=values["snooze_until"],  # type: ignore[arg-type]
            created_at=values["action_at"],  # type: ignore[arg-type]
        )
        self.events.append(event)
        return event

    async def list_history(
        self,
        _session: AsyncSession,
        *,
        company_id: UUID,
        condition_key: UUID,
        limit: int,
    ) -> tuple[BeaconLifecycleEvent, ...]:
        self.history_company_ids.append(company_id)
        return tuple(
            event
            for event in reversed(self.events)
            if event.condition_key == condition_key
        )[:limit]


async def current_signal() -> BeaconSignal:
    service = query_service(FakeRepository(snapshot()))
    return (
        await service.evaluate_current(
            object(),  # type: ignore[arg-type]
            company_id=COMPANY_ID,
            measured_at=NOW,
        )
    )[0]


def review_context(*permissions: str) -> AuthorizationContext:
    value = context(*permissions)
    object.__setattr__(value, "membership", SimpleNamespace(id=uuid4()))
    return value


@pytest.mark.asyncio
async def test_read_permission_alone_cannot_mutate_lifecycle() -> None:
    signal = await current_signal()
    service = BeaconLifecycleService(
        repository=LifecycleRepository(),  # type: ignore[arg-type]
        query_service=CurrentSignalQuery(signal),  # type: ignore[arg-type]
    )
    with pytest.raises(PermissionDeniedError):
        await service.record(
            FakeSession(),  # type: ignore[arg-type]
            context=review_context(AnalyticsPermission.READ),
            command=RecordBeaconLifecycleAction(
                signal_id=signal.id,
                evidence_digest=signal.evidence_digest,
                action=BeaconLifecycleAction.ACKNOWLEDGE,
            ),
            now=NOW,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action",
    [BeaconLifecycleAction.ACKNOWLEDGE, BeaconLifecycleAction.REVIEW],
)
async def test_authorized_acknowledge_and_review_append_immutable_events(
    action: BeaconLifecycleAction,
) -> None:
    signal = await current_signal()
    repository = LifecycleRepository()
    query = CurrentSignalQuery(signal)
    service = BeaconLifecycleService(
        repository=repository,  # type: ignore[arg-type]
        query_service=query,  # type: ignore[arg-type]
    )
    event = await service.record(
        FakeSession(),  # type: ignore[arg-type]
        context=review_context(BeaconPermission.REVIEW),
        command=RecordBeaconLifecycleAction(
            signal_id=signal.id,
            evidence_digest=signal.evidence_digest,
            action=action,
        ),
        now=NOW,
    )

    assert event.action is action
    assert event.signal_id == signal.id
    assert event.evidence_digest == signal.evidence_digest
    assert query.company_ids == [COMPANY_ID]
    assert repository.events == [event]


@pytest.mark.asyncio
async def test_snooze_requires_future_timestamp_and_exact_current_evidence() -> None:
    signal = await current_signal()
    service = BeaconLifecycleService(
        repository=LifecycleRepository(),  # type: ignore[arg-type]
        query_service=CurrentSignalQuery(signal),  # type: ignore[arg-type]
    )
    auth = review_context(BeaconPermission.REVIEW)
    with pytest.raises(BeaconSnoozeInvalidError):
        await service.record(
            FakeSession(),  # type: ignore[arg-type]
            context=auth,
            command=RecordBeaconLifecycleAction(
                signal_id=signal.id,
                evidence_digest=signal.evidence_digest,
                action=BeaconLifecycleAction.SNOOZE,
                snooze_until=NOW,
            ),
            now=NOW,
        )
    with pytest.raises(BeaconSignalStaleError):
        await service.record(
            FakeSession(),  # type: ignore[arg-type]
            context=auth,
            command=RecordBeaconLifecycleAction(
                signal_id=signal.id,
                evidence_digest="0" * 64,
                action=BeaconLifecycleAction.ACKNOWLEDGE,
            ),
            now=NOW,
        )
    with pytest.raises(BeaconSignalNotFoundError):
        await BeaconLifecycleService(
            repository=LifecycleRepository(),  # type: ignore[arg-type]
            query_service=CurrentSignalQuery(None),  # type: ignore[arg-type]
        ).record(
            FakeSession(),  # type: ignore[arg-type]
            context=auth,
            command=RecordBeaconLifecycleAction(
                signal_id=uuid4(),
                evidence_digest="0" * 64,
                action=BeaconLifecycleAction.REVIEW,
            ),
            now=NOW,
        )


def lifecycle_event(
    signal: BeaconSignal,
    *,
    action: BeaconLifecycleAction,
    action_at: datetime,
    snooze_until: datetime | None = None,
) -> BeaconLifecycleEvent:
    return BeaconLifecycleEvent(
        id=uuid4(),
        company_id=COMPANY_ID,
        condition_key=signal.condition_key,
        signal_id=signal.id,
        rule_code=signal.rule_code,
        signal_source=signal.source,
        evidence_digest=signal.evidence_digest,
        action=action,
        actor_membership_id=uuid4(),
        action_at=action_at,
        snooze_until=snooze_until,
        created_at=action_at,
    )


@pytest.mark.asyncio
async def test_active_snooze_suppresses_only_exact_evidence_then_expires() -> None:
    facts = FakeRepository(snapshot())
    lifecycle = FakeLifecycleRepository()
    service = BeaconQueryService(
        facts,
        lifecycle,  # type: ignore[arg-type]
    )
    signals = await service.evaluate_current(
        object(),  # type: ignore[arg-type]
        company_id=COMPANY_ID,
        measured_at=NOW,
    )
    target = signals[0]
    lifecycle.events[target.condition_key] = lifecycle_event(
        target,
        action=BeaconLifecycleAction.SNOOZE,
        action_at=NOW - timedelta(minutes=1),
        snooze_until=NOW + timedelta(hours=1),
    )

    queue = await service.get_attention_queue(
        object(),  # type: ignore[arg-type]
        context=review_context(AnalyticsPermission.READ),
        now=NOW,
    )
    assert target.id not in {signal.id for signal in queue.active}
    assert [signal.id for signal in queue.snoozed] == [target.id]
    expired = await service.get_attention_queue(
        object(),  # type: ignore[arg-type]
        context=review_context(AnalyticsPermission.READ),
        now=NOW + timedelta(hours=2),
    )
    assert target.condition_key in {signal.condition_key for signal in expired.active}
    assert expired.snoozed == ()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "expected_status"),
    [
        (BeaconLifecycleAction.ACKNOWLEDGE, "acknowledged"),
        (BeaconLifecycleAction.REVIEW, "reviewed"),
    ],
)
async def test_acknowledged_and_reviewed_conditions_remain_visible(
    action: BeaconLifecycleAction,
    expected_status: str,
) -> None:
    facts = FakeRepository(snapshot())
    lifecycle = FakeLifecycleRepository()
    service = BeaconQueryService(facts, lifecycle)  # type: ignore[arg-type]
    signals = await service.evaluate_current(
        object(),  # type: ignore[arg-type]
        company_id=COMPANY_ID,
        measured_at=NOW,
    )
    target = signals[0]
    lifecycle.events[target.condition_key] = lifecycle_event(
        target,
        action=action,
        action_at=NOW,
    )

    queue = await service.get_attention_queue(
        object(),  # type: ignore[arg-type]
        context=review_context(AnalyticsPermission.READ),
        now=NOW,
    )
    projected = next(item for item in queue.active if item.id == target.id)
    assert projected.lifecycle.status == expected_status
    assert not projected.lifecycle.temporarily_suppressed


@pytest.mark.asyncio
async def test_history_is_company_scoped_and_deterministic() -> None:
    signal = await current_signal()
    repository = LifecycleRepository()
    repository.events.extend(
        [
            lifecycle_event(
                signal,
                action=BeaconLifecycleAction.ACKNOWLEDGE,
                action_at=NOW - timedelta(minutes=2),
            ),
            lifecycle_event(
                signal,
                action=BeaconLifecycleAction.REVIEW,
                action_at=NOW - timedelta(minutes=1),
            ),
        ]
    )
    service = BeaconLifecycleService(
        repository=repository,  # type: ignore[arg-type]
        query_service=CurrentSignalQuery(signal),  # type: ignore[arg-type]
    )
    history = await service.history(
        object(),  # type: ignore[arg-type]
        context=review_context(AnalyticsPermission.READ),
        condition_key=signal.condition_key,
        limit=50,
    )

    assert [event.action for event in history] == [
        BeaconLifecycleAction.REVIEW,
        BeaconLifecycleAction.ACKNOWLEDGE,
    ]
    assert repository.history_company_ids == [COMPANY_ID]
