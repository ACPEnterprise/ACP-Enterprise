from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ProviderKnowledge(StrEnum):
    NOT_SUBMITTED = "NOT_SUBMITTED"
    TRANSPORT_FAILED_BEFORE_ACCEPTANCE = "TRANSPORT_FAILED_BEFORE_ACCEPTANCE"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    UNCERTAIN = "UNCERTAIN"
    ACKNOWLEDGED = "ACKNOWLEDGED"


class RetryDisposition(StrEnum):
    SAFE_RETRY = "SAFE_RETRY"
    UNSAFE_TO_RETRY = "UNSAFE_TO_RETRY"
    RECONCILE_BEFORE_RETRY = "RECONCILE_BEFORE_RETRY"
    NO_RETRY = "NO_RETRY"


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    policy_id: str
    version: str
    retry_before_acceptance: bool
    maximum_attempts: int | None = None

    def __post_init__(self) -> None:
        if not self.policy_id or not self.version:
            raise ValueError("retry policy identity and version are required")
        if self.maximum_attempts is not None and self.maximum_attempts < 1:
            raise ValueError("maximum attempts must be positive when configured")


@dataclass(frozen=True, slots=True)
class ProviderAttemptEvidence:
    provider: str
    provider_version: str
    operation_identity: str
    request_digest: str
    knowledge: ProviderKnowledge
    attempt_sequence: int
    provider_reference_digest: str | None = None

    def __post_init__(self) -> None:
        if not self.provider or not self.provider_version or not self.operation_identity:
            raise ValueError("provider and operation authority are required")
        if len(self.request_digest) != 64:
            raise ValueError("request digest must be a SHA-256 digest")
        if self.attempt_sequence < 1:
            raise ValueError("attempt sequence must be positive")


def retry_disposition(
    evidence: ProviderAttemptEvidence,
    policy: RetryPolicy,
) -> RetryDisposition:
    if evidence.knowledge is ProviderKnowledge.TRANSPORT_FAILED_BEFORE_ACCEPTANCE:
        if not policy.retry_before_acceptance:
            return RetryDisposition.NO_RETRY
        if (
            policy.maximum_attempts is not None
            and evidence.attempt_sequence >= policy.maximum_attempts
        ):
            return RetryDisposition.NO_RETRY
        return RetryDisposition.SAFE_RETRY
    if evidence.knowledge is ProviderKnowledge.UNCERTAIN:
        return RetryDisposition.RECONCILE_BEFORE_RETRY
    if evidence.knowledge in {
        ProviderKnowledge.ACCEPTED,
        ProviderKnowledge.ACKNOWLEDGED,
        ProviderKnowledge.REJECTED,
    }:
        return RetryDisposition.NO_RETRY
    return RetryDisposition.UNSAFE_TO_RETRY
