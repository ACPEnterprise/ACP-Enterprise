from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.engineering_control.records import (
    EngineeringApprovalState,
    EngineeringExecutionState,
)
from app.engineering_control.review.contracts import (
    EngineeringReviewDecision,
    EngineeringReviewState,
)
from app.engineering_control.schemas import EngineeringCancellationReason


class MobileEngineeringSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)


class MobileCommandSummary(MobileEngineeringSchema):
    id: UUID
    ecid: str
    command_type: str
    repository_key: str
    expected_branch: str
    expected_head: str
    requested_code_changes: bool
    approval_state: EngineeringApprovalState
    execution_state: EngineeringExecutionState
    created_at: datetime
    expires_at: datetime
    version: int


class MobileCommandDetail(MobileCommandSummary):
    owner_instruction: str
    instruction_digest: str
    request_digest: str
    updated_at: datetime
    approved_at: datetime | None
    approved_by_user_id: UUID | None
    canceled_at: datetime | None
    canceled_by_user_id: UUID | None
    cancellation_reason_code: str | None
    result_reference: str | None
    can_approve: bool
    can_cancel: bool
    execution_connected: bool = False


class MobileCommandPage(MobileEngineeringSchema):
    items: tuple[MobileCommandSummary, ...]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total_count: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class MobileEngineeringConnectivity(MobileEngineeringSchema):
    state: str
    session_id: UUID | None
    last_contact_at: datetime | None
    heartbeat_at: datetime | None


class MobileOwnerReviewSummary(MobileEngineeringSchema):
    id: UUID
    command_id: UUID
    execution_id: UUID
    ecid: str
    provider_identifier: str
    result_status: str
    result_disposition: str
    validation_summary: dict[str, object]
    file_boundary: tuple[str, ...]
    state: EngineeringReviewState
    created_at: datetime
    decision: EngineeringReviewDecision | None
    decided_at: datetime | None


class MobileOwnerReviewPage(MobileEngineeringSchema):
    items: tuple[MobileOwnerReviewSummary, ...]
    connectivity: MobileEngineeringConnectivity
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total_count: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class MobileWorkstreamSummary(MobileEngineeringSchema):
    command_id: UUID
    ecid: str
    display_name: str
    repository_key: str
    expected_branch: str
    expected_head: str
    approval_state: str
    lifecycle_state: str
    progress_summary: str
    owner_action_required: bool
    next_owner_action: str
    connection_state: str
    assigned_worker_id: UUID | None
    execution_id: UUID | None
    offer_or_lease_state: str | None
    heartbeat_at: datetime | None
    review_id: UUID | None
    review_state: str | None
    authorization_id: UUID | None
    authorization_status: str | None
    repository_operation_id: UUID | None
    repository_operation_status: str | None
    failure_classification: str | None
    resulting_commit_sha: str | None
    repository_clean: bool | None
    owner_attention_required: bool
    updated_at: datetime
    pipeline_status: str
    desired_state: str
    control_pending: bool
    available_actions: tuple[str, ...]
    runtime_state: str
    runtime_version: int | None
    acknowledged_action: str | None
    acknowledged_at: datetime | None
    acknowledgement_expires_at: datetime | None
    worker_health: str | None
    progress_percent: int | None
    current_activity: str | None
    acknowledgement_latency_ms: int | None = None
    execution_latency_ms: int | None = None
    validation_latency_ms: int | None = None
    deployment_latency_ms: int | None = None
    worker_uptime_seconds: int | None = None
    reconnect_count: int = 0


class MobileWorkstreamDetail(MobileWorkstreamSummary):
    owner_instruction: str
    requested_code_changes: bool
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    timeline: tuple[dict[str, object], ...]


class MobileWorkstreamActionRequest(MobileEngineeringSchema):
    action: str = Field(pattern=r"^(start|pause|resume|cancel)$")
    reason: str | None = Field(default=None, max_length=240)


class MobileWorkstreamActionResult(MobileEngineeringSchema):
    command_id: UUID
    action: str
    desired_state: str
    accepted: bool
    message: str
    updated_at: datetime


class MobileWorkstreamPage(MobileEngineeringSchema):
    items: tuple[MobileWorkstreamSummary, ...]
    connectivity: MobileEngineeringConnectivity
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total_count: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class MissionNotificationItem(MobileEngineeringSchema):
    id: UUID
    command_id: UUID
    kind: str
    severity: str
    status: str
    created_at: datetime
    escalated_at: datetime | None
    acknowledged_at: datetime | None
    read_at: datetime | None
    archived_at: datetime | None
    version: int


class MissionNotificationPage(MobileEngineeringSchema):
    items: tuple[MissionNotificationItem, ...]
    unread_count: int = Field(ge=0)
    escalated_count: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total_count: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class MissionNotificationAcknowledgement(MobileEngineeringSchema):
    expected_version: int = Field(ge=1)


class MissionNotificationTransition(MobileEngineeringSchema):
    expected_version: int = Field(ge=1)
    action: str = Field(pattern=r"^(read|archive)$")


class MobileApprovalRequest(MobileEngineeringSchema):
    expected_version: int = Field(ge=1)
    instruction_digest: str = Field(min_length=1, max_length=128)
    request_digest: str = Field(min_length=1, max_length=128)
    repository_key: str = Field(min_length=1, max_length=100)
    expected_branch: str = Field(min_length=1, max_length=255)
    expected_head: str = Field(pattern=r"^[0-9a-f]{40}$")
    requested_code_changes: bool


class MobileCancellationRequest(MobileEngineeringSchema):
    expected_version: int = Field(ge=1)
    reason_code: EngineeringCancellationReason


class MilestoneDefinitionCreate(MobileEngineeringSchema):
    title: str = Field(min_length=1, max_length=160)
    objective: str = Field(min_length=1, max_length=10000)
    owning_workstream: str | None = Field(default=None, min_length=1, max_length=100)
    owning_branch: str | None = Field(default=None, min_length=1, max_length=255)
    authority: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    validation: tuple[str, ...] = ()
    deliverables: tuple[str, ...] = ()
    stop_conditions: tuple[str, ...] = ()
    expected_completion_evidence: tuple[str, ...] = ()
    approved: bool = False
    requested_code_changes: bool = True


class RoadmapCreate(MobileEngineeringSchema):
    title: str = Field(min_length=1, max_length=160)
    repository_key: str = Field(min_length=1, max_length=100)
    expected_branch: str = Field(min_length=1, max_length=255)
    expected_head: str = Field(pattern=r"^[0-9a-f]{40}$")
    milestones: tuple[MilestoneDefinitionCreate, ...] = Field(min_length=1)


class RoadmapItem(MobileEngineeringSchema):
    id: UUID
    title: str
    repository_key: str
    expected_branch: str
    expected_head: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class MilestoneItem(MobileEngineeringSchema):
    id: UUID
    roadmap_id: UUID
    position: int
    title: str
    objective: str
    owning_workstream: str
    owning_branch: str
    authority: tuple[str, ...]
    constraints: tuple[str, ...]
    dependencies: tuple[str, ...]
    validation: tuple[str, ...]
    deliverables: tuple[str, ...]
    stop_conditions: tuple[str, ...]
    expected_completion_evidence: tuple[str, ...]
    status: str
    definition_approved: bool
    requested_code_changes: bool
    externally_adoptable: bool = False
    external_evidence: str | None
    command_id: UUID | None
    version: int
    started_at: datetime | None
    completed_at: datetime | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    external_adoption: "ExternalAdoptionItem | None" = None


class ExternalAdoptionCreate(MobileEngineeringSchema):
    repository_key: str = Field(min_length=1, max_length=100)
    branch: str = Field(min_length=1, max_length=255)
    starting_head: str = Field(pattern=r"^[0-9a-f]{40}$")
    starting_repository_clean: bool
    worktree_identity: str | None = Field(default=None, max_length=500)
    owning_external_workstream: str = Field(min_length=1, max_length=160)
    declared_scope: tuple[str, ...] = Field(min_length=1, max_length=50)
    protected_boundaries: tuple[str, ...] = Field(min_length=1, max_length=50)
    expected_deliverables: tuple[str, ...] = Field(min_length=1, max_length=50)
    validation_requirements: tuple[str, ...] = Field(min_length=1, max_length=50)
    evidence_format: str = Field(min_length=1, max_length=80)
    responsible_source: str = Field(min_length=1, max_length=160)


class ExternalEvidenceCreate(MobileEngineeringSchema):
    expected_adoption_version: int = Field(ge=1)
    status: str = Field(
        pattern=r"^(pending_start|externally_running|externally_validating|externally_blocked|completed)$"
    )
    progress_percent: int = Field(ge=0, le=100)
    current_activity: str | None = Field(default=None, max_length=500)
    starting_head: str = Field(pattern=r"^[0-9a-f]{40}$")
    current_head: str = Field(pattern=r"^[0-9a-f]{40}$")
    commits: tuple[str, ...] = Field(max_length=100)
    files_changed: tuple[str, ...] = Field(max_length=500)
    validation_results: tuple[str, ...] = Field(max_length=100)
    dependencies: tuple[str, ...] = Field(max_length=100)
    blockers: tuple[str, ...] = Field(max_length=100)
    completion_evidence: tuple[str, ...] = Field(max_length=100)
    owner_action_required: bool
    repository_state: str = Field(pattern=r"^(clean|dirty)$")
    occurred_at: datetime
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9._:-]{8,128}$")
    correction: bool = False
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ExternalAdoptionItem(MobileEngineeringSchema):
    id: UUID
    repository_key: str
    branch: str
    starting_head: str
    current_head: str
    worktree_identity: str | None
    owning_external_workstream: str
    status: str
    progress_percent: int
    current_activity: str | None
    last_evidence_at: datetime | None
    responsible_source: str
    adopted_at: datetime
    version: int
    mission_control_dispatched: bool = False
    validation_summary: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    evidence_stale: bool = False
    next_owner_action: str = "none"


class RoadmapPage(MobileEngineeringSchema):
    roadmaps: tuple[RoadmapItem, ...]
    milestones: tuple[MilestoneItem, ...]
    waiting_for_me: tuple[MilestoneItem, ...]
    current_milestones: tuple[MilestoneItem, ...]
    next_approved_milestones: tuple[MilestoneItem, ...]
    future_milestones: tuple[MilestoneItem, ...]
    completed_milestones: tuple[MilestoneItem, ...]
    blocked_milestones: tuple[MilestoneItem, ...]
    actionable_count: int = Field(ge=0)
    projection_warnings: tuple[str, ...] = ()


class MilestoneActionRequest(MobileEngineeringSchema):
    action: str = Field(
        pattern=r"^(start|approve|reject|request_revision|skip|pause|resume|cancel|archive)$"
    )
    expected_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=240)
