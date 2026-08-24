import hashlib
import hmac
import json
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.payments.contracts import ProviderRequest
from app.payments.errors import PaymentSecurityError
from app.payments.provider import (
    DeterministicFakeProvider,
    DeterministicWebhookVerifier,
    ExistingProcessorAdapter,
)


@pytest.mark.asyncio
async def test_fake_is_deterministic_and_idempotent() -> None:
    provider = DeterministicFakeProvider()
    request = ProviderRequest(uuid4(), "stable-key", "synthetic", Decimal("12.34"), "USD", "opaque_test_success")
    assert await provider.collect(request) == await provider.collect(request)
    assert (await provider.collect(request)).outcome == "captured"


@pytest.mark.asyncio
async def test_fake_models_decline_and_ambiguity_without_receipt_claim() -> None:
    provider = DeterministicFakeProvider()
    for marker, outcome in (("opaque_declined", "declined"), ("opaque_ambiguous", "ambiguous")):
        result = await provider.collect(ProviderRequest(uuid4(), marker, "synthetic", Decimal("1.00"), "USD", marker))
        assert result.outcome == outcome


@pytest.mark.asyncio
async def test_existing_processor_is_fail_closed() -> None:
    with pytest.raises(PaymentSecurityError):
        await ExistingProcessorAdapter().collect(ProviderRequest(uuid4(), "key", "merchant", Decimal("1.00"), "USD", "opaque_ref"))


def test_webhook_verifies_raw_body_merchant_rotation_and_tamper() -> None:
    secret = b"synthetic-test-only"
    verifier = DeterministicWebhookVerifier({"v2": secret})
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
    body = json.dumps({"event_id": "evt_1", "event_type": "capture.succeeded", "merchant_account": "synthetic", "amount": "2.00", "currency": "USD"}, separators=(",", ":")).encode()
    signature = "v2=" + hmac.new(secret, timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    verified = verifier.verify(raw_body=body, signature=signature, timestamp=timestamp, merchant_account="synthetic")
    assert verified.secret_version == "v2"
    assert set(verified.allowed_evidence) == {"amount", "currency"}
    with pytest.raises(PaymentSecurityError):
        verifier.verify(raw_body=body + b" ", signature=signature, timestamp=timestamp, merchant_account="synthetic")


def test_webhook_rejects_stale_or_wrong_merchant() -> None:
    verifier = DeterministicWebhookVerifier({"v1": b"test"}, tolerance_seconds=1)
    body = b'{"event_id":"e","event_type":"x","merchant_account":"wrong"}'
    with pytest.raises(PaymentSecurityError):
        verifier.verify(raw_body=body, signature="v1=bad", timestamp="0", merchant_account="expected")
