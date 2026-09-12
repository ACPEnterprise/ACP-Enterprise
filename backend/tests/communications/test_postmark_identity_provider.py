import io
import os
import urllib.error
from pathlib import Path
from uuid import uuid4

import pytest

from app.communications.postmark import PostmarkIdentityProvider
from app.platform.notifications.providers import (
    NotificationMessage,
    NotificationProviderOutcome,
    NotificationProviderTransportError,
)


def provider(tmp_path: Path) -> PostmarkIdentityProvider:
    secret = tmp_path / "token"
    secret.write_text("test-token", encoding="utf-8")
    secret.chmod(0o600)
    assert secret.stat().st_uid == os.geteuid()
    return PostmarkIdentityProvider(
        token_file=str(secret),
        sender="ACP Employee <no-reply@allcountyhomeservices.com>",
    )


@pytest.mark.asyncio
async def test_rejects_customer_message_without_network(tmp_path: Path) -> None:
    result = await provider(tmp_path).deliver(
        NotificationMessage(
            notification_id=uuid4(),
            notification_type="appointment_reminder",
            template_identifier="x",
            recipient="customer@example.com",
            payload={},
            correlation_id=uuid4(),
        )
    )
    assert result.outcome is NotificationProviderOutcome.REJECTED
    assert result.error_code == "identity_provider_scope_rejected"


def test_rejects_unapproved_sender_and_unsafe_secret(tmp_path: Path) -> None:
    secret = tmp_path / "token"
    secret.write_text("test-token", encoding="utf-8")
    secret.chmod(0o644)
    configured = PostmarkIdentityProvider(
        token_file=str(secret),
        sender="ACP Employee <no-reply@allcountyhomeservices.com>",
    )
    with pytest.raises(ValueError, match="permissions"):
        configured._token()
    with pytest.raises(ValueError, match="owner-approved"):
        PostmarkIdentityProvider(
            token_file=str(secret),
            sender="Marketing <marketing@allcountyhomeservices.com>",
        )


@pytest.mark.asyncio
async def test_definitive_postmark_422_is_safe_to_retry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    body = io.BytesIO(b'{"ErrorCode":300,"Message":"private provider detail"}')
    error = urllib.error.HTTPError(
        "https://api.postmarkapp.com/email", 422, "rejected", {}, body
    )
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(error)
    )
    with pytest.raises(NotificationProviderTransportError) as captured:
        await provider(tmp_path).deliver(
            NotificationMessage(
                notification_id=uuid4(),
                notification_type="identity.onboarding_invitation",
                template_identifier="x",
                recipient="employee@example.com",
                payload={},
                correlation_id=uuid4(),
                subject="Invite",
                plain_text="Safe",
                html="<p>Safe</p>",
            )
        )
    assert captured.value.error_code == "postmark_request_rejected_422_code_300"
    assert captured.value.retryable is False
    assert captured.value.submission_possible is False


@pytest.mark.asyncio
async def test_password_reset_is_accepted_by_identity_only_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    configured = provider(tmp_path)
    monkeypatch.setattr(
        configured,
        "_request",
        lambda **_kwargs: {"ErrorCode": 0, "MessageID": "withheld-provider-id"},
    )
    result = await configured.deliver(
        NotificationMessage(
            notification_id=uuid4(),
            notification_type="identity.password_reset",
            template_identifier="identity-password-reset-v1",
            recipient="employee@example.com",
            payload={"password_reset_token_id": str(uuid4())},
            correlation_id=uuid4(),
            subject="Reset password",
            plain_text="Safe fixed content",
            html="<p>Safe fixed content</p>",
        )
    )
    assert result.outcome is NotificationProviderOutcome.ACCEPTED
    assert result.provider_message_id == "withheld-provider-id"
