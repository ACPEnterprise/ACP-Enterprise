from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class WorkerIdentityState(StrEnum):
    REGISTERED = "registered"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class WorkerCredentialState(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


@dataclass(frozen=True)
class IssuedCredentialMetadata:
    verifier: str
    verifier_algorithm: str
    public_key_id: str


class WorkerCredentialIssuer(Protocol):
    """Secret-store seam. It returns verifier/public metadata, never raw secrets."""

    async def issue(
        self, *, identity_id: UUID, credential_version: int
    ) -> IssuedCredentialMetadata: ...
