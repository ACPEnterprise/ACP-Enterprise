from __future__ import annotations

import hashlib

import pytest

from app.core.config import Settings
from app.platform.reliability.failure_injection import (
    FailurePoint,
    InjectedReliabilityFailure,
    inject_failure,
)
from app.platform.reliability.provider import (
    ProviderAttemptEvidence,
    ProviderKnowledge,
    RetryDisposition,
    RetryPolicy,
    retry_disposition,
)


def _evidence(knowledge: ProviderKnowledge, attempt: int = 1) -> ProviderAttemptEvidence:
    return ProviderAttemptEvidence(
        provider="synthetic-provider",
        provider_version="v1",
        operation_identity="operation-safe-identity",
        request_digest=hashlib.sha256(b"safe synthetic request").hexdigest(),
        knowledge=knowledge,
        attempt_sequence=attempt,
    )


def test_provider_uncertainty_never_becomes_blind_retry() -> None:
    policy = RetryPolicy("provider-neutral", "v1", retry_before_acceptance=True)
    assert retry_disposition(_evidence(ProviderKnowledge.UNCERTAIN), policy) is RetryDisposition.RECONCILE_BEFORE_RETRY
    assert retry_disposition(_evidence(ProviderKnowledge.ACCEPTED), policy) is RetryDisposition.NO_RETRY
    assert retry_disposition(_evidence(ProviderKnowledge.ACKNOWLEDGED), policy) is RetryDisposition.NO_RETRY


def test_pre_acceptance_retry_requires_explicit_versioned_policy() -> None:
    allowed = RetryPolicy("provider-neutral", "v1", retry_before_acceptance=True, maximum_attempts=2)
    denied = RetryPolicy("financial-provider", "v1", retry_before_acceptance=False)
    evidence = _evidence(ProviderKnowledge.TRANSPORT_FAILED_BEFORE_ACCEPTANCE)
    assert retry_disposition(evidence, allowed) is RetryDisposition.SAFE_RETRY
    assert retry_disposition(_evidence(evidence.knowledge, 2), allowed) is RetryDisposition.NO_RETRY
    assert retry_disposition(evidence, denied) is RetryDisposition.NO_RETRY


def test_failure_injection_is_mechanically_test_only() -> None:
    with pytest.raises(InjectedReliabilityFailure, match=FailurePoint.REDIS_UNAVAILABLE.value):
        inject_failure(FailurePoint.REDIS_UNAVAILABLE, Settings(environment="test"))
    with pytest.raises(RuntimeError, match="prohibited outside test"):
        inject_failure(
            FailurePoint.PROVIDER_ACCEPTANCE_UNCERTAIN,
            Settings(
                environment="development",
                access_token_signing_key="x" * 32,
                security_token_hmac_key="y" * 32,
            ),
        )
