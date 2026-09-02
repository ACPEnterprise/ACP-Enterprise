import hashlib
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.communications.catalog import (
    OPERATIONAL_MESSAGE_CATALOG,
    ChannelEligibility,
    catalog_fingerprint,
    select_channel,
)
from app.communications.delivery import (
    ProviderDeliveryEvent,
    ProviderRecipientControlEvent,
    ProviderWebhookService,
    RecipientControlKind,
    SyntheticWebhookVerifier,
)
from app.communications.readiness import (
    ProviderConfiguration,
    ReadinessState,
    configuration_from_settings,
    project_readiness,
)
from app.communications.suppression import recipient_suppression_repository
from app.communications.templates import (
    TemplateSecurityError,
    render_operational_notice,
)
from app.communications.types import CommunicationChannel, CommunicationType
from app.core.config import settings
from app.platform.notifications.repository import NotificationOutboxRepository


def test_catalog_has_governed_owners_and_stable_fingerprint() -> None:
    assert (
        OPERATIONAL_MESSAGE_CATALOG[CommunicationType.TECHNICIAN_EN_ROUTE].owner_domain
        == "dispatch"
    )
    assert (
        OPERATIONAL_MESSAGE_CATALOG[CommunicationType.INVOICE_READY].owner_domain
        == "invoicing"
    )
    assert len(catalog_fingerprint()) == 64
    assert catalog_fingerprint() == catalog_fingerprint()


def test_channel_selection_honors_suppression_and_governed_fallback() -> None:
    result = select_channel(
        policy=OPERATIONAL_MESSAGE_CATALOG[CommunicationType.APPOINTMENT_CONFIRMATION],
        preferred=CommunicationChannel.SMS,
        eligibility=(
            ChannelEligibility(CommunicationChannel.SMS, True, True, suppressed=True),
            ChannelEligibility(CommunicationChannel.EMAIL, True, True),
        ),
        fallback_order=(CommunicationChannel.SMS, CommunicationChannel.EMAIL),
    )
    assert result.channel is CommunicationChannel.EMAIL
    assert result.fallback_from is CommunicationChannel.SMS
    assert result.reason == "governed_fallback"


def test_marketing_consent_does_not_authorize_transactional_channel() -> None:
    try:
        select_channel(
            policy=OPERATIONAL_MESSAGE_CATALOG[
                CommunicationType.APPOINTMENT_CONFIRMATION
            ],
            preferred=CommunicationChannel.SMS,
            eligibility=(
                ChannelEligibility(
                    CommunicationChannel.SMS,
                    available=True,
                    transactional_allowed=False,
                    marketing_consented=True,
                ),
            ),
            fallback_order=(CommunicationChannel.SMS,),
        )
    except ValueError as error:
        assert "No eligible transactional" in str(error)
    else:
        raise AssertionError("marketing consent must not authorize operations")


def test_health_never_reports_synthetic_provider_as_ready() -> None:
    result = project_readiness(ProviderConfiguration())
    assert result.email is ReadinessState.EMAIL_PROVIDER_NOT_CONFIGURED
    assert result.sms is ReadinessState.SMS_PROVIDER_NOT_CONFIGURED
    assert result.overall is ReadinessState.DEGRADED
    assert result.synthetic_only is True


def test_health_requires_all_real_admission_evidence() -> None:
    result = project_readiness(
        ProviderConfiguration(True, True, True, True, True, True, True)
    )
    assert result.overall is ReadinessState.READY
    assert result.synthetic_only is False


def test_settings_projection_exposes_readiness_not_secret_references() -> None:
    configured = settings.model_copy(
        update={
            "communications_delivery_enabled": True,
            "communications_email_provider_identity": "synthetic-email",
            "communications_email_credential_reference": "secret://email-canary",
            "communications_email_sender_verified": True,
            "communications_email_domain_verified": True,
            "communications_sms_provider_identity": "synthetic-sms",
            "communications_sms_credential_reference": "secret://sms-canary",
            "communications_sms_sender_identity": "synthetic-sender",
            "communications_sms_registration_verified": True,
            "communications_webhook_enabled": True,
            "communications_webhook_secret_reference": "secret://webhook-canary",
        }
    )
    projection = configuration_from_settings(configured)
    assert project_readiness(projection).overall is ReadinessState.READY
    assert "secret" not in repr(projection).lower()


def test_operational_templates_are_channel_specific_and_injection_safe() -> None:
    rendered = render_operational_notice(
        message_type=CommunicationType.TECHNICIAN_EN_ROUTE,
        company_display_name="ACP Service",
        protected_url="https://preview.example.test/appointments/opaque",
        expected_origin="https://preview.example.test",
    )
    assert rendered.sms_text == (
        "ACP Service: Your technician is on the way. "
        "https://preview.example.test/appointments/opaque"
    )
    assert len(rendered.content_digest) == 64
    try:
        render_operational_notice(
            message_type=CommunicationType.TECHNICIAN_EN_ROUTE,
            company_display_name="ACP\r\nBcc: attacker@example.test",
        )
    except TemplateSecurityError:
        pass
    else:
        raise AssertionError("header injection must fail closed")


def test_sms_stop_contract_carries_digest_not_raw_destination() -> None:
    event = ProviderRecipientControlEvent(
        company_id=uuid4(),
        provider_event_key="provider-event-1",
        destination_digest="a" * 64,
        channel="sms",
        kind=RecipientControlKind.OPT_OUT,
        occurred_at=datetime.now(timezone.utc),
    )
    event.validate()
    assert not hasattr(event, "destination")


@pytest.mark.asyncio
async def test_synthetic_webhook_rejects_forgery_and_forwards_safe_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = b'{"synthetic":"delivered"}'
    event = ProviderDeliveryEvent(
        company_id=uuid4(),
        provider_reference="synthetic-message-1",
        provider_event_key="synthetic-event-1",
        outcome="delivered",
        occurred_at=datetime.now(timezone.utc),
    )
    apply = AsyncMock(return_value=True)
    monkeypatch.setattr(NotificationOutboxRepository, "apply_provider_event", apply)
    service = ProviderWebhookService()
    verifier = SyntheticWebhookVerifier()
    with pytest.raises(ValueError, match="authenticity"):
        await service.ingest(
            SimpleNamespace(),
            verifier=verifier,
            headers={"x-synthetic-signature": "forged"},
            body=body,
            event=event,
        )
    assert await service.ingest(
        SimpleNamespace(),
        verifier=verifier,
        headers={"x-synthetic-signature": hashlib.sha256(body).hexdigest()},
        body=body,
        event=event,
    )
    assert apply.await_count == 1


@pytest.mark.asyncio
async def test_authenticated_stop_is_digest_only_replay_safe_control(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = b'{"synthetic":"STOP"}'
    now = datetime.now(timezone.utc)
    event = ProviderRecipientControlEvent(
        company_id=uuid4(),
        provider_event_key="synthetic-stop-1",
        destination_digest="a" * 64,
        channel="sms",
        kind=RecipientControlKind.OPT_OUT,
        occurred_at=now,
    )
    record = AsyncMock(return_value=(SimpleNamespace(), True))
    monkeypatch.setattr(recipient_suppression_repository, "record", record)
    created = await ProviderWebhookService().ingest_recipient_control(
        SimpleNamespace(),
        verifier=SyntheticWebhookVerifier(),
        headers={"x-synthetic-signature": hashlib.sha256(body).hexdigest()},
        body=body,
        event=event,
        recorded_at=now,
    )
    assert created is True
    decision = record.await_args.args[1]
    assert decision.destination_digest == "a" * 64
    assert decision.active is True
    assert not hasattr(decision, "destination")
