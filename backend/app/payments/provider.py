import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import cast

from app.payments.contracts import (
    PaymentProvider,
    ProviderOutcome,
    ProviderRequest,
    ProviderResult,
    VerifiedWebhook,
)
from app.payments.errors import PaymentSecurityError


class ExistingProcessorAdapter(PaymentProvider):
    """Activation interface for the retained processor; deliberately fail-closed."""

    name = "existing_processor"

    async def collect(self, request: ProviderRequest) -> ProviderResult:
        raise PaymentSecurityError("Live processor activation is not configured.")

    async def refund(self, request: ProviderRequest) -> ProviderResult:
        raise PaymentSecurityError("Live processor activation is not configured.")

    async def lookup(self, provider_operation_id: str) -> ProviderResult:
        raise PaymentSecurityError("Live processor activation is not configured.")


class DeterministicFakeProvider(PaymentProvider):
    """Synthetic provider used by tests; outcomes derive only from opaque test refs."""

    name = "deterministic_fake"

    def __init__(self) -> None:
        self._results: dict[str, ProviderResult] = {}

    async def collect(self, request: ProviderRequest) -> ProviderResult:
        return self._execute(request, "collect")

    async def refund(self, request: ProviderRequest) -> ProviderResult:
        return self._execute(request, "refund")

    async def lookup(self, provider_operation_id: str) -> ProviderResult:
        return self._results.get(
            provider_operation_id,
            ProviderResult("failed", provider_operation_id, "not_found", _digest(provider_operation_id)),
        )

    def _execute(self, request: ProviderRequest, operation: str) -> ProviderResult:
        prior = self._results.get(request.provider_idempotency_key)
        if prior:
            return prior
        marker = request.opaque_payment_method.lower()
        outcome = next((x for x in ("ambiguous", "declined", "failed") if x in marker), None)
        outcome = outcome or "captured"
        provider_id = f"fake_{operation}_{request.operation_id.hex}"
        result = ProviderResult(
            cast(ProviderOutcome, outcome), provider_id, None if outcome == "captured" else f"synthetic_{outcome}",
            _digest(f"{operation}:{request.provider_idempotency_key}:{outcome}"),
        )
        self._results[request.provider_idempotency_key] = result
        self._results[provider_id] = result
        return result


class DeterministicWebhookVerifier:
    """Test-only raw-body verifier. Secrets are injected and never persisted."""

    def __init__(self, secrets: dict[str, bytes], tolerance_seconds: int = 300) -> None:
        self._secrets = secrets
        self._tolerance = tolerance_seconds

    def verify(self, *, raw_body: bytes, signature: str, timestamp: str, merchant_account: str) -> VerifiedWebhook:
        try:
            sent_at = datetime.fromtimestamp(int(timestamp), timezone.utc)
        except (ValueError, OverflowError) as exc:
            raise PaymentSecurityError("Invalid webhook timestamp.") from exc
        if abs((datetime.now(timezone.utc) - sent_at).total_seconds()) > self._tolerance:
            raise PaymentSecurityError("Stale webhook timestamp.")
        version, _, supplied = signature.partition("=")
        secret = self._secrets.get(version)
        if not secret or not supplied:
            raise PaymentSecurityError("Unknown webhook secret version.")
        expected = hmac.new(secret, timestamp.encode() + b"." + raw_body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, supplied):
            raise PaymentSecurityError("Invalid webhook signature.")
        try:
            data = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise PaymentSecurityError("Malformed webhook payload.") from exc
        allowed = {key: str(data[key]) for key in ("provider_operation_id", "amount", "currency") if key in data}
        if data.get("merchant_account") != merchant_account:
            raise PaymentSecurityError("Webhook merchant account mismatch.")
        if not data.get("event_id") or not data.get("event_type"):
            raise PaymentSecurityError("Unsupported webhook evidence.")
        return VerifiedWebhook(
            provider_event_id=str(data["event_id"]), merchant_account=merchant_account,
            event_type=str(data["event_type"]), occurred_at=sent_at,
            allowed_evidence=allowed, evidence_digest=hashlib.sha256(raw_body).hexdigest(),
            secret_version=version,
        )


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
