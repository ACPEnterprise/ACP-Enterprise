from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.communications.delivery import (
    SyntheticNotificationProvider,
    TransactionalDeliveryService,
)
from app.communications.templates import (
    TemplateSecurityError,
    render_employee_invitation,
    render_protected_document_notice,
)
from app.platform.notifications.providers import (
    NotificationDeliveryResult,
    NotificationProviderOutcome,
)
from app.platform.notifications.repository import NotificationOutboxRepository


def invitation(**overrides: str):
    facts = {
        "recipient_display_name": "Synthetic <Employee>",
        "company_display_name": "ACP Test & Company",
        "activation_url": "https://preview.example.test/activate?token=canary",
        "expected_origin": "https://preview.example.test",
        "expiration_copy": "This invitation expires in 24 hours.",
    }
    facts.update(overrides)
    return render_employee_invitation(**facts)


def test_invitation_template_is_deterministic_escaped_and_versioned() -> None:
    first = invitation()
    second = invitation()
    assert first == second
    assert first.template_version == "identity-onboarding-invitation-v1"
    assert first.content_digest == second.content_digest
    assert "<Employee>" not in first.html
    assert "&lt;Employee&gt;" in first.html
    assert "<script" not in first.html
    assert "password" not in first.plain_text.lower()


@pytest.mark.parametrize(
    "override",
    [
        {"recipient_display_name": "Unsafe\nBcc: victim@example.test"},
        {"activation_url": "http://preview.example.test/activate"},
        {"activation_url": "https://foreign.example.test/activate"},
        {"activation_url": "https://user:secret@preview.example.test/activate"},
    ],
)
def test_invitation_template_rejects_header_and_link_attacks(
    override: dict[str, str],
) -> None:
    with pytest.raises(TemplateSecurityError):
        invitation(**override)


def test_document_notice_binds_exact_artifact_digest_without_path() -> None:
    rendered = render_protected_document_notice(
        template_identifier="estimate-protected-delivery",
        title="Estimate 1042",
        protected_url="https://preview.example.test/documents/opaque-reference",
        expected_origin="https://preview.example.test",
        artifact_digest="a" * 64,
    )
    assert rendered.template_version == "estimate-protected-delivery-v1"
    assert "/tmp/" not in rendered.plain_text
    assert len(rendered.content_digest) == 64


class Resolver:
    async def render(self, _record):
        return invitation()


def claimed_record():
    return SimpleNamespace(
        id=uuid4(),
        status="claimed",
        claim_token=uuid4(),
        notification_type="identity.onboarding_invitation",
        template_identifier="identity-onboarding-invitation-v1",
        template_version="identity-onboarding-invitation-v1",
        recipient="synthetic@example.test",
        payload={"invitation_id": str(uuid4()), "protected_envelope": True},
        correlation_id=uuid4(),
        provider_idempotency_key="synthetic-key",
        submitted_at=None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outcome", "method"),
    [
        (NotificationProviderOutcome.ACCEPTED, "mark_accepted"),
        (NotificationProviderOutcome.DELIVERED, "mark_sent"),
        (NotificationProviderOutcome.DEFERRED, "schedule_retry"),
        (NotificationProviderOutcome.BOUNCED, "mark_failed"),
        (NotificationProviderOutcome.REJECTED, "mark_failed"),
        (NotificationProviderOutcome.UNCERTAIN, "mark_ambiguous"),
    ],
)
async def test_synthetic_provider_outcomes_map_to_truthful_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    outcome: NotificationProviderOutcome,
    method: str,
) -> None:
    record = claimed_record()
    provider = SyntheticNotificationProvider(outcome)
    methods = {
        name: AsyncMock(return_value=True)
        for name in (
            "record_provider_submission",
            "mark_accepted",
            "mark_sent",
            "schedule_retry",
            "mark_failed",
            "mark_ambiguous",
        )
    }
    for name, mocked in methods.items():
        monkeypatch.setattr(NotificationOutboxRepository, name, mocked)
    result = await TransactionalDeliveryService().deliver_claimed(
        SimpleNamespace(),
        record=record,
        provider=provider,
        resolver=Resolver(),
        now=datetime.now(timezone.utc),
    )
    assert result.outcome == outcome.value
    assert methods[method].await_count == 1
    assert provider.messages[0].payload == {}
    assert provider.messages[0].content_digest
    assert provider.messages[0].provider_idempotency_key == "synthetic-key"


@pytest.mark.asyncio
async def test_exact_synthetic_delivery_preserves_logical_identity() -> None:
    record = claimed_record()
    provider = SyntheticNotificationProvider(NotificationProviderOutcome.ACCEPTED)
    result = await provider.deliver(SimpleNamespace(notification_id=record.id))
    assert result.provider_message_id is not None
    assert str(record.id) in result.provider_message_id


@pytest.mark.asyncio
async def test_provider_acceptance_without_reference_becomes_uncertain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = claimed_record()
    provider = SimpleNamespace(
        deliver=AsyncMock(
            return_value=NotificationDeliveryResult(
                outcome=NotificationProviderOutcome.ACCEPTED
            )
        )
    )
    submission = AsyncMock(return_value=True)
    ambiguous = AsyncMock(return_value=True)
    monkeypatch.setattr(
        NotificationOutboxRepository, "record_provider_submission", submission
    )
    monkeypatch.setattr(NotificationOutboxRepository, "mark_ambiguous", ambiguous)
    result = await TransactionalDeliveryService().deliver_claimed(
        SimpleNamespace(),
        record=record,
        provider=provider,
        resolver=Resolver(),
        now=datetime.now(timezone.utc),
    )
    assert result.outcome == "uncertain"
    assert ambiguous.await_args.kwargs["error_code"] == "provider_reference_missing"
