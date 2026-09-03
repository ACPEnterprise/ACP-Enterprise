from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest

from app.communications.contracts import CommunicationRequest
from app.communications.errors import (
    CommunicationAuthorizationError,
    CommunicationConflictError,
    CommunicationNotFoundError,
    CommunicationValidationError,
)
from app.communications.repository import CommunicationRepository
from app.communications.service import POLICIES, CommunicationService
from app.communications.types import CommunicationChannel, CommunicationType
from app.main import app
from app.platform.notifications.repository import NotificationOutboxRepository
from app.platform.permissions.authorization import (
    PermissionDeniedError,
    authorization_service,
)
from app.platform.permissions.catalog import permission_catalog
from app.platform.permissions.codes import CommunicationsPermission


class FakeSession:
    def __init__(self) -> None:
        self.rollbacks = 0
        self.added = []

    async def rollback(self) -> None:
        self.rollbacks += 1

    def add(self, record) -> None:
        self.added.append(record)

    @asynccontextmanager
    async def begin(self):
        yield


@pytest.mark.asyncio
async def test_operational_measurement_is_deterministic_and_read_only() -> None:
    branch_id = uuid4()
    ctx = context()
    repository = SimpleNamespace(
        operational_measurement=AsyncMock(
            return_value=(
                {
                    "submitted": 4,
                    "accepted": 3,
                    "delivered": 2,
                    "failed": 1,
                    "bounced": 1,
                    "rejected": 1,
                    "suppressed": 2,
                    "ambiguous": 1,
                    "retryable": 3,
                    "recovered": 1,
                    "webhook_replay": 2,
                },
                {
                    "pending": 1,
                    "retry_scheduled": 1,
                    "accepted": 1,
                    "sent": 2,
                    "failed": 1,
                    "suppressed": 2,
                    "ambiguous": 1,
                },
            )
        )
    )
    service = CommunicationService(repository)
    first = await service.operational_measurement(
        FakeSession(), context=ctx, branch_id=branch_id
    )
    second = await service.operational_measurement(
        FakeSession(), context=ctx, branch_id=branch_id
    )
    assert first == second
    assert first.bounced_or_invalid_recipient == 2
    assert first.final_pending == 2
    assert first.final_delivered == 2
    assert first.final_uncertain == 1
    assert first.recovered == 1
    assert len(first.measurement_fingerprint) == 64
    assert repository.operational_measurement.await_count == 2


@pytest.mark.asyncio
async def test_operational_measurement_rejects_foreign_branch_before_query() -> None:
    repository = SimpleNamespace(operational_measurement=AsyncMock())
    service = CommunicationService(repository)
    with pytest.raises(CommunicationAuthorizationError):
        await service.operational_measurement(
            FakeSession(), context=context(can_access=False), branch_id=uuid4()
        )
    repository.operational_measurement.assert_not_awaited()


def context(*, can_access: bool = True):
    return SimpleNamespace(
        company=SimpleNamespace(id=uuid4()),
        user=SimpleNamespace(id=uuid4()),
        can_access_branch=lambda _branch_id: can_access,
    )


def request(
    *,
    branch_id: UUID | None = None,
    communication_type: CommunicationType = CommunicationType.APPOINTMENT_CONFIRMATION,
    channel: CommunicationChannel = CommunicationChannel.SMS,
) -> CommunicationRequest:
    return CommunicationRequest(
        communication_type=communication_type,
        channel=channel,
        customer_id=uuid4(),
        contact_id=uuid4(),
        branch_id=branch_id or uuid4(),
        source_event_id=uuid4(),
        request_key="initial",
        scheduled_at=datetime.now(timezone.utc),
    )


def outbox_record(payload: dict[str, object], identity: str):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid4(),
        payload=payload,
        recipient=str(payload["recipient"]),
        idempotency_key=identity,
        status="pending",
        retry_count=0,
        terminal_failure=False,
        scheduled_at=now,
        sent_at=None,
        failed_at=None,
        last_error_code=None,
        last_error_category=None,
        created_at=now,
    )


def repository_for(ctx, spec: CommunicationRequest, *, consent="granted"):
    source = SimpleNamespace(
        id=spec.source_event_id,
        event_type="appointment.booked",
        entity_type="appointment",
        entity_id=uuid4(),
        company_id=ctx.company.id,
        branch_id=spec.branch_id,
        correlation_id=uuid4(),
        payload={"customer_id": str(spec.customer_id)},
    )

    contact = SimpleNamespace(
        normalized_email="owner@example.test",
        email="owner@example.test",
        normalized_mobile_phone="+15555550123",
        mobile_phone="5555550123",
    )
    consent_event = (
        SimpleNamespace(id=uuid4(), payload={"decision": consent})
        if consent is not None
        else None
    )
    return SimpleNamespace(
        source_event=AsyncMock(return_value=source),
        source_customer_id=AsyncMock(return_value=spec.customer_id),
        customer_contact=AsyncMock(return_value=(SimpleNamespace(), contact)),
        is_recipient_suppressed=AsyncMock(return_value=False),
        latest_consent=AsyncMock(return_value=consent_event),
        list_scoped=AsyncMock(return_value=[]),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entity_type",
    [
        "appointment",
        "job",
        "estimate",
        "invoice",
        "service_agreement",
        "service_agreement_billing_occurrence",
        "dispatch_assignment",
    ],
)
async def test_missing_payload_customer_resolves_from_supported_source_aggregate(
    entity_type: str,
) -> None:
    customer_id = uuid4()
    session = SimpleNamespace(scalar=AsyncMock(return_value=customer_id))
    source = SimpleNamespace(
        entity_type=entity_type,
        entity_id=uuid4(),
        payload={},
    )

    assert (
        await CommunicationRepository.source_customer_id(
            session,
            source=source,
            company_id=uuid4(),
            branch_id=uuid4(),
        )
        == customer_id
    )
    session.scalar.assert_awaited_once()


@pytest.mark.asyncio
async def test_request_is_structured_consent_checked_and_idempotent(
    monkeypatch,
) -> None:
    ctx = context()
    spec = request()
    repository = repository_for(ctx, spec)
    service = CommunicationService(repository)
    captured: list[dict[str, object]] = []

    async def enqueue(_session, **kwargs):
        captured.append(kwargs)
        return outbox_record(kwargs["payload"], kwargs["idempotency_key"]), True

    monkeypatch.setattr(NotificationOutboxRepository, "enqueue", enqueue)
    first_session = FakeSession()
    first = await service.request(first_session, context=ctx, request=spec)
    second = await service.request(FakeSession(), context=ctx, request=spec)

    assert first.request_identity == second.request_identity
    assert captured[0]["idempotency_key"] == captured[1]["idempotency_key"]
    assert captured[0]["notification_type"] == "communications.appointment_confirmation"
    assert captured[0]["template_identifier"] == "appointment-confirmation-v1"
    assert captured[0]["company_id"] == ctx.company.id
    assert captured[0]["branch_id"] == spec.branch_id
    assert captured[0]["payload"]["consent_event_id"]
    assert "message" not in captured[0]["payload"]
    assert "provider" not in captured[0]["payload"]
    assert first_session.added[0].event_type == "communication.requested"
    assert "recipient" not in first_session.added[0].payload


def test_launch_policy_is_bounded_to_authoritative_domain_events() -> None:
    assert {item: policy.source_event_types for item, policy in POLICIES.items()} == {
        CommunicationType.APPOINTMENT_CONFIRMATION: frozenset({"appointment.booked"}),
        CommunicationType.APPOINTMENT_REMINDER: frozenset(
            {"appointment.booked", "appointment.rescheduled"}
        ),
        CommunicationType.APPOINTMENT_RESCHEDULED: frozenset(
            {"appointment.rescheduled"}
        ),
        CommunicationType.APPOINTMENT_CANCELLED: frozenset({"appointment.cancelled"}),
        CommunicationType.TECHNICIAN_EN_ROUTE: frozenset({"technician.en_route"}),
        CommunicationType.TECHNICIAN_ARRIVED: frozenset({"technician.arrived"}),
        CommunicationType.ESTIMATE_ACTION_REQUESTED: frozenset({"estimate.sent"}),
        CommunicationType.ESTIMATE_STATUS_NOTICE: frozenset(
            {"estimate.approved", "estimate.rejected", "estimate.expired"}
        ),
    }
    assert all(policy.consent_required for policy in POLICIES.values())


@pytest.mark.asyncio
@pytest.mark.parametrize("consent", [None, "withdrawn"])
async def test_request_fails_closed_without_current_consent(consent) -> None:
    ctx = context()
    spec = request()
    service = CommunicationService(repository_for(ctx, spec, consent=consent))
    with pytest.raises(CommunicationAuthorizationError, match="consent"):
        await service.request(FakeSession(), context=ctx, request=spec)


@pytest.mark.asyncio
async def test_request_fails_closed_for_current_recipient_suppression() -> None:
    ctx = context()
    spec = request()
    repository = repository_for(ctx, spec)
    repository.is_recipient_suppressed = AsyncMock(return_value=True)
    with pytest.raises(CommunicationAuthorizationError, match="suppression"):
        await CommunicationService(repository).request(
            FakeSession(), context=ctx, request=spec
        )


@pytest.mark.asyncio
async def test_request_fails_closed_for_missing_recipient() -> None:
    ctx = context()
    spec = request(channel=CommunicationChannel.EMAIL)
    repository = repository_for(ctx, spec)
    repository.customer_contact = AsyncMock(
        return_value=(
            SimpleNamespace(),
            SimpleNamespace(
                normalized_email=None,
                email=None,
                normalized_mobile_phone=None,
                mobile_phone=None,
            ),
        )
    )
    with pytest.raises(CommunicationValidationError, match="recipient"):
        await CommunicationService(repository).request(
            FakeSession(), context=ctx, request=spec
        )


@pytest.mark.asyncio
async def test_wrong_company_or_missing_source_fails_closed() -> None:
    ctx = context()
    spec = request()
    repository = repository_for(ctx, spec)
    repository.source_event = AsyncMock(return_value=None)
    with pytest.raises(CommunicationNotFoundError, match="Source-domain"):
        await CommunicationService(repository).request(
            FakeSession(), context=ctx, request=spec
        )
    assert repository.source_event.await_args.kwargs == {
        "event_id": spec.source_event_id,
        "company_id": ctx.company.id,
        "branch_id": spec.branch_id,
    }


@pytest.mark.asyncio
async def test_source_aggregate_customer_must_match_requested_customer() -> None:
    ctx = context()
    spec = request()
    repository = repository_for(ctx, spec)
    repository.source_customer_id = AsyncMock(return_value=uuid4())

    with pytest.raises(CommunicationValidationError, match="does not belong"):
        await CommunicationService(repository).request(
            FakeSession(), context=ctx, request=spec
        )
    repository.customer_contact.assert_not_awaited()


@pytest.mark.asyncio
async def test_unresolved_source_aggregate_customer_fails_closed() -> None:
    ctx = context()
    spec = request()
    repository = repository_for(ctx, spec)
    repository.source_customer_id = AsyncMock(return_value=None)

    with pytest.raises(CommunicationValidationError, match="could not be resolved"):
        await CommunicationService(repository).request(
            FakeSession(), context=ctx, request=spec
        )
    repository.customer_contact.assert_not_awaited()


@pytest.mark.asyncio
async def test_general_request_rejects_non_delivery_channels() -> None:
    ctx = context()
    spec = request(
        communication_type=CommunicationType.ESTIMATE_ACTION_REQUESTED,
        channel=CommunicationChannel.PROTECTED_LINK,
    )
    repository = repository_for(ctx, spec)

    with pytest.raises(CommunicationValidationError, match="Email and SMS only"):
        await CommunicationService(repository).request(
            FakeSession(), context=ctx, request=spec
        )
    repository.source_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_unauthorized_branch_fails_before_source_lookup() -> None:
    ctx = context(can_access=False)
    spec = request()
    repository = repository_for(ctx, spec)
    with pytest.raises(CommunicationAuthorizationError, match="Branch"):
        await CommunicationService(repository).request(
            FakeSession(), context=ctx, request=spec
        )
    repository.source_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_unsupported_source_event_type_fails_closed() -> None:
    ctx = context()
    spec = request()
    repository = repository_for(ctx, spec)
    source = await repository.source_event()
    source.event_type = "job.completed"
    repository.source_event = AsyncMock(return_value=source)
    with pytest.raises(CommunicationValidationError, match="does not support"):
        await CommunicationService(repository).request(
            FakeSession(), context=ctx, request=spec
        )


@pytest.mark.asyncio
async def test_history_preserves_company_branch_and_customer_scope() -> None:
    ctx = context()
    spec = request()
    repository = repository_for(ctx, spec)
    await CommunicationService(repository).list(
        FakeSession(),
        context=ctx,
        branch_id=spec.branch_id,
        customer_id=spec.customer_id,
        limit=25,
    )
    assert repository.list_scoped.await_args.kwargs == {
        "company_id": ctx.company.id,
        "branch_id": spec.branch_id,
        "customer_id": spec.customer_id,
        "limit": 25,
    }


@pytest.mark.asyncio
async def test_replayed_identity_with_changed_inputs_fails_closed(monkeypatch) -> None:
    ctx = context()
    spec = request()
    repository = repository_for(ctx, spec)

    async def enqueue(_session, **kwargs):
        record = outbox_record(kwargs["payload"], kwargs["idempotency_key"])
        record.payload = {**record.payload, "request_digest": "different"}
        return record, False

    monkeypatch.setattr(NotificationOutboxRepository, "enqueue", enqueue)
    with pytest.raises(CommunicationConflictError, match="different evidence"):
        await CommunicationService(repository).request(
            FakeSession(), context=ctx, request=spec
        )


def test_communications_permissions_are_canonical_and_separate() -> None:
    codes = {definition.code for definition in permission_catalog.definitions}
    assert CommunicationsPermission.READ in codes
    assert CommunicationsPermission.MANAGE in codes
    assert CommunicationsPermission.READ != CommunicationsPermission.MANAGE


@pytest.mark.parametrize(
    ("granted", "required", "allowed"),
    [
        (frozenset(), CommunicationsPermission.READ, False),
        (frozenset(), CommunicationsPermission.MANAGE, False),
        (
            frozenset({CommunicationsPermission.READ}),
            CommunicationsPermission.READ,
            True,
        ),
        (
            frozenset({CommunicationsPermission.READ}),
            CommunicationsPermission.MANAGE,
            False,
        ),
        (
            frozenset({CommunicationsPermission.MANAGE}),
            CommunicationsPermission.READ,
            False,
        ),
        (
            frozenset({CommunicationsPermission.MANAGE}),
            CommunicationsPermission.MANAGE,
            True,
        ),
    ],
)
def test_communications_read_and_manage_authority_are_independent(
    granted: frozenset[str], required: str, allowed: bool
) -> None:
    authorization = SimpleNamespace(has_permission=lambda code: code in granted)
    if allowed:
        authorization_service.require_permission(authorization, required)
    else:
        with pytest.raises(PermissionDeniedError):
            authorization_service.require_permission(authorization, required)


@pytest.mark.asyncio
async def test_communications_api_fails_closed_without_authentication() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        read = await client.get("/api/v1/communications/history")
        manage = await client.post(
            "/api/v1/communications/requests",
            json={
                "communication_type": "appointment_confirmation",
                "channel": "sms",
                "customer_id": str(uuid4()),
                "contact_id": str(uuid4()),
                "branch_id": str(uuid4()),
                "source_event_id": str(uuid4()),
                "request_key": "test",
                "scheduled_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    assert read.status_code == 401
    assert manage.status_code == 401


def test_openapi_exposes_only_bounded_request_and_history_contracts() -> None:
    paths = app.openapi()["paths"]
    assert "/api/v1/communications/requests" in paths
    assert "/api/v1/communications/history" in paths
    assert set(paths["/api/v1/communications/requests"]) == {"post"}
    assert set(paths["/api/v1/communications/history"]) == {"get"}
