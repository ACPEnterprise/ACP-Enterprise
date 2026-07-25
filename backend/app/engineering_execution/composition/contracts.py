from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class CompositionState(StrEnum):
    CREATED = "created"
    EXPIRED = "expired"
    REVOKED = "revoked"


class CompositionReceiptStatus(StrEnum):
    ACCEPTED = "accepted"


class ProviderAttemptState(StrEnum):
    PREPARED = "prepared"
    STARTING = "starting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    QUARANTINED = "quarantined"


class ProviderProgressPhase(StrEnum):
    PREPARING = "preparing"
    STARTING = "starting"
    EXECUTING = "executing"
    VALIDATING = "validating"
    FINALIZING = "finalizing"


class ProviderResultStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProviderResultDisposition(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    QUARANTINED = "quarantined"


@dataclass(frozen=True)
class CompositionIntegrityEvidence:
    """Verifier-ready metadata; no key material or custom cryptography."""

    method: str
    key_reference: str | None = None
    proof: str | None = None


class CompositionIntegrityProvider(Protocol):
    def evidence_for(self, *, composition_digest: str) -> CompositionIntegrityEvidence:
        """Return bounded proof metadata without exposing signing material."""


class DigestOnlyCompositionIntegrityProvider:
    """Honest foundation default: digest evidence, not a signature or MAC."""

    def evidence_for(self, *, composition_digest: str) -> CompositionIntegrityEvidence:
        del composition_digest
        return CompositionIntegrityEvidence(method="digest_only")
