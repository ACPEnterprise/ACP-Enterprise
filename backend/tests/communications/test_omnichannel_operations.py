from datetime import datetime, timezone
from uuid import uuid4

from app.communications.catalog import (
    OPERATIONAL_MESSAGE_CATALOG,
    ChannelEligibility,
    catalog_fingerprint,
    select_channel,
)
from app.communications.delivery import (
    ProviderRecipientControlEvent,
    RecipientControlKind,
)
from app.communications.readiness import (
    ProviderConfiguration,
    ReadinessState,
    project_readiness,
)
from app.communications.templates import (
    TemplateSecurityError,
    render_operational_notice,
)
from app.communications.types import CommunicationChannel, CommunicationType


def test_catalog_has_governed_owners_and_stable_fingerprint() -> None:
    assert OPERATIONAL_MESSAGE_CATALOG[CommunicationType.TECHNICIAN_EN_ROUTE].owner_domain == "dispatch"
    assert OPERATIONAL_MESSAGE_CATALOG[CommunicationType.INVOICE_READY].owner_domain == "invoicing"
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
            policy=OPERATIONAL_MESSAGE_CATALOG[CommunicationType.APPOINTMENT_CONFIRMATION],
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
