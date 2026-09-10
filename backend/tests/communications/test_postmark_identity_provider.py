import os
from pathlib import Path
from uuid import uuid4

import pytest

from app.communications.postmark import PostmarkIdentityProvider
from app.platform.notifications.providers import NotificationMessage, NotificationProviderOutcome


def provider(tmp_path: Path) -> PostmarkIdentityProvider:
    secret = tmp_path / "token"
    secret.write_text("test-token", encoding="utf-8")
    secret.chmod(0o600)
    assert secret.stat().st_uid == os.geteuid()
    return PostmarkIdentityProvider(token_file=str(secret), sender="ACP Employee <no-reply@allcountyhomeservices.com>")


@pytest.mark.asyncio
async def test_rejects_customer_message_without_network(tmp_path: Path) -> None:
    result = await provider(tmp_path).deliver(NotificationMessage(notification_id=uuid4(), notification_type="appointment_reminder", template_identifier="x", recipient="customer@example.com", payload={}, correlation_id=uuid4()))
    assert result.outcome is NotificationProviderOutcome.REJECTED
    assert result.error_code == "identity_provider_scope_rejected"


def test_rejects_unapproved_sender_and_unsafe_secret(tmp_path: Path) -> None:
    secret = tmp_path / "token"; secret.write_text("test-token", encoding="utf-8"); secret.chmod(0o644)
    configured = PostmarkIdentityProvider(token_file=str(secret), sender="ACP Employee <no-reply@allcountyhomeservices.com>")
    with pytest.raises(ValueError, match="permissions"):
        configured._token()
    with pytest.raises(ValueError, match="owner-approved"):
        PostmarkIdentityProvider(token_file=str(secret), sender="Marketing <marketing@allcountyhomeservices.com>")
