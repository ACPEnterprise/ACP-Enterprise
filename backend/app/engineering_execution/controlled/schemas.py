from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ControlledSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PrepareControlledOfferRequest(ControlledSchema):
    workspace_id: str = Field(min_length=3, max_length=100)
    lease_seconds: int = Field(default=300, ge=30, le=900)


class ControlledOfferResponse(ControlledSchema):
    id: UUID
    command_id: UUID
    execution_id: UUID
    workspace_id: str
    command_type: str
    capability_required: str
    state: str
    expires_at: datetime
    lease_seconds: int
    created_at: datetime


class AdoptControlledResultRequest(ControlledSchema):
    command_id: UUID
    ecid: str = Field(pattern=r"^ECID-[0-9]{4}-[0-9]{6,}$")
    offer_id: UUID
    lease_id: UUID
    starting_head: str = Field(pattern=r"^[0-9a-f]{40}$")
    commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    commit_parent: str = Field(pattern=r"^[0-9a-f]{40}$")
    remote_head: str = Field(pattern=r"^[0-9a-f]{40}$")
    boundary_version: int = Field(ge=1)
    boundary_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    boundary_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_completed_at: datetime
    provider_evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    workspace_clean: bool
    output: dict[str, object]
    idempotency_key: str = Field(min_length=1, max_length=160)


class AdoptControlledResultResponse(ControlledSchema):
    result_id: UUID
    execution_id: UUID
    outcome: str
    repository_mutated: bool
    result_commit: str
    provider_completed_at: datetime
    adopted_at: datetime
    review_id: UUID
