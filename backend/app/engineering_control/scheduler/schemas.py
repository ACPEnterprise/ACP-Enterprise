from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Classification = Literal[
    "current/adoptable",
    "completed",
    "superseded",
    "orphaned",
    "ambiguous",
    "reconciliation-required",
]


class SchedulerSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RecordClassification(SchedulerSchema):
    record_type: str
    record_id: UUID
    classification: Classification
    milestone_code: str | None = None
    reason: str


class ProposedTransition(SchedulerSchema):
    record_type: str
    record_id: UUID | None = None
    milestone_code: str | None = None
    from_state: str | None = None
    to_state: str
    reason: str
    destructive: bool = False


class CRM2PreservationEvidence(SchedulerSchema):
    milestone_ids: tuple[UUID, ...] = ()
    command_ids: tuple[UUID, ...] = ()
    runtime_ids: tuple[UUID, ...] = ()
    reservation_ids: tuple[UUID, ...] = ()
    allocation_ids: tuple[UUID, ...] = ()
    worker_capacity_ids: tuple[UUID, ...] = ()
    proposed_mutation_ids: tuple[UUID, ...] = ()
    preserved: bool
    reason: str


class CapacityFinding(SchedulerSchema):
    permanent_capacity_identity: str
    binding_id: UUID | None = None
    worker_capacity_id: UUID | None = None
    state: str
    reason: str


class SchedulerReconciliationReport(SchedulerSchema):
    mode: Literal["dry_run", "apply"]
    scheduler_version: str
    scheduler_fingerprint: str
    before_counts: dict[str, int]
    proposed_after_counts: dict[str, int]
    classifications: tuple[RecordClassification, ...]
    proposed_transitions: tuple[ProposedTransition, ...]
    capacity_mappings: tuple[CapacityFinding, ...]
    crm2_preservation: CRM2PreservationEvidence
    orphaned_record_ids: tuple[UUID, ...]
    ambiguous_record_ids: tuple[UUID, ...]
    destructive_operation_count: int = Field(ge=0)
    mutations_performed: int = Field(ge=0)
