"""Preview Postmark adapter restricted to ACP identity/security email."""

from __future__ import annotations

import asyncio
import json
import os
import stat
import urllib.error
import urllib.request
from pathlib import Path

from app.platform.notifications.providers import (
    NotificationDeliveryResult,
    NotificationMessage,
    NotificationProviderOutcome,
    NotificationProviderTransportError,
)

POSTMARK_API_ORIGIN = "https://api.postmarkapp.com"
IDENTITY_NOTIFICATION_TYPES = frozenset(
    {
        "identity.onboarding_invitation",
        "identity.email_change_verification",
        "identity.password_reset",
    }
)


class PostmarkIdentityProvider:
    """Send only approved identity/security messages; never Customer communications."""

    def __init__(self, *, token_file: str, sender: str) -> None:
        self._token_file = Path(token_file)
        self._sender = sender.strip()
        if self._sender != "ACP Employee <no-reply@allcountyhomeservices.com>":
            raise ValueError("Postmark identity sender is not owner-approved.")

    def _token(self) -> str:
        metadata = self._token_file.stat()
        if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) & 0o077:
            raise ValueError("Postmark credential permissions are unsafe.")
        if metadata.st_uid != os.geteuid():
            raise ValueError("Postmark credential ownership is unsafe.")
        token = self._token_file.read_text(encoding="utf-8").strip()
        if not token or "\n" in token:
            raise ValueError("Postmark credential is invalid.")
        return token

    def _request(self, *, path: str, method: str = "GET", payload: dict[str, str] | None = None) -> dict[str, object]:
        body = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(
            f"{POSTMARK_API_ORIGIN}{path}", data=body, method=method,
            headers={"X-Postmark-Server-Token": self._token(), "Accept": "application/json", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                decoded = json.loads(response.read().decode())
                return decoded if isinstance(decoded, dict) else {}
        except urllib.error.HTTPError as error:
            if error.code in {401, 403}:
                raise NotificationProviderTransportError("postmark_authentication_failed", retryable=False, submission_possible=False) from error
            if error.code == 429 or error.code >= 500:
                raise NotificationProviderTransportError("postmark_temporarily_unavailable", retryable=True, submission_possible=method == "POST") from error
            provider_code = None
            try:
                response = json.loads(error.read().decode())
                value = response.get("ErrorCode") if isinstance(response, dict) else None
                provider_code = value if isinstance(value, int) else None
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
            safe_code = f"postmark_request_rejected_{error.code}"
            if provider_code is not None:
                safe_code += f"_code_{provider_code}"
            # Postmark HTTP 4xx responses are definitive request rejections: the
            # provider did not accept a message and no delivery can follow.
            raise NotificationProviderTransportError(
                safe_code, retryable=False, submission_possible=False
            ) from error
        except (OSError, TimeoutError) as error:
            raise NotificationProviderTransportError("postmark_transport_uncertain", retryable=False, submission_possible=method == "POST") from error

    async def verify_authentication(self) -> bool:
        result = await asyncio.to_thread(self._request, path="/server")
        return bool(result.get("ID"))

    async def deliver(self, message: NotificationMessage) -> NotificationDeliveryResult:
        if message.notification_type not in IDENTITY_NOTIFICATION_TYPES:
            return NotificationDeliveryResult(outcome=NotificationProviderOutcome.REJECTED, error_code="identity_provider_scope_rejected")
        result = await asyncio.to_thread(
            self._request, path="/email", method="POST",
            payload={"From": self._sender, "To": message.recipient, "Subject": message.subject, "TextBody": message.plain_text, "HtmlBody": message.html, "MessageStream": "outbound", "Tag": "acp-identity-security"},
        )
        message_id = result.get("MessageID")
        error_code = result.get("ErrorCode")
        if error_code != 0 or not isinstance(message_id, str) or not message_id:
            return NotificationDeliveryResult(outcome=NotificationProviderOutcome.REJECTED, error_code="postmark_submission_rejected")
        return NotificationDeliveryResult(outcome=NotificationProviderOutcome.ACCEPTED, provider_message_id=message_id)


async def _verify_from_settings() -> int:
    from app.core.config import get_settings

    settings = get_settings()
    if settings.identity_onboarding_delivery_provider != "postmark":
        raise SystemExit("Postmark identity provider is not enabled.")
    provider = PostmarkIdentityProvider(
        token_file=settings.identity_email_postmark_token_file or "",
        sender=settings.identity_email_sender or "",
    )
    if not await provider.verify_authentication():
        raise SystemExit("Postmark authentication verification failed.")
    print("Postmark identity provider authentication verified; no email sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_verify_from_settings()))
