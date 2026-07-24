from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.worker_identity.contracts import WorkerCredentialState, WorkerIdentityState


@dataclass(frozen=True)
class WorkerIdentityRecord:
    id: UUID
    company_id: UUID
    name: str
    state: WorkerIdentityState
    registered_by_user_id: UUID
    version: int
    registered_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class WorkerCredentialRecord:
    id: UUID
    company_id: UUID
    identity_id: UUID
    version: int
    state: WorkerCredentialState
    verifier: str
    verifier_algorithm: str
    public_key_id: str
    issued_at: datetime
    expires_at: datetime
    activated_at: datetime | None
    revoked_at: datetime | None
    expired_at: datetime | None
    updated_at: datetime
