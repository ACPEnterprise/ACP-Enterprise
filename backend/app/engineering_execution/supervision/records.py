from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.execution_providers.contracts import ProviderCapability
from app.execution_providers.runtime import (
    ProviderCredentialStatus,
    ProviderRuntimeState,
)

from .contracts import ProviderSessionState, SupervisorState


@dataclass(frozen=True)
class LiveClientSupervisorRecord:
    id: UUID
    company_id: UUID
    worker_id: UUID
    state: SupervisorState
    version: int
    started_at: datetime | None
    recovered_at: datetime | None
    last_transition_at: datetime
    failure_classification: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ProviderSessionRecord:
    id: UUID
    company_id: UUID
    supervisor_id: UUID
    composition_id: UUID
    attempt_id: UUID
    worker_id: UUID
    lease_id: UUID
    provider_identifier: str
    effective_capabilities: tuple[ProviderCapability, ...]
    approved_code_changes: bool
    state: ProviderSessionState
    runtime_state: ProviderRuntimeState
    credential_status: ProviderCredentialStatus
    provider_ready: bool
    provider_session_reference: str | None
    version: int
    created_at: datetime
    opening_at: datetime | None
    ready_at: datetime | None
    active_at: datetime | None
    closing_at: datetime | None
    closed_at: datetime | None
    expires_at: datetime
    failure_classification: str | None
    updated_at: datetime
