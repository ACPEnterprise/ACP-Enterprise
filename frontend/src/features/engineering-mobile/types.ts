export type MobileReviewState =
  "awaiting_approval" | "approved" | "rejected" | "canceled" | "expired";

export type MobileExecutionState = "execution_not_connected";

export type MobileCancellationReason =
  "owner_requested" | "scope_changed" | "no_longer_needed";

export interface MobileReviewSummary {
  id: string;
  ecid: string;
  command_type: string;
  repository_key: string;
  expected_branch: string;
  expected_head: string;
  requested_code_changes: boolean;
  approval_state: MobileReviewState;
  execution_state: MobileExecutionState;
  created_at: string;
  expires_at: string;
  version: number;
}

export interface MobileReviewDetail extends MobileReviewSummary {
  owner_instruction: string;
  instruction_digest: string;
  request_digest: string;
  updated_at: string;
  approved_at: string | null;
  approved_by_user_id: string | null;
  canceled_at: string | null;
  canceled_by_user_id: string | null;
  cancellation_reason_code: string | null;
  can_approve: boolean;
  can_cancel: boolean;
  execution_connected: false;
  result_reference: string | null;
}

export type MobileCommandStatus = MobileReviewDetail;

export interface MobileReviewPage {
  items: readonly MobileReviewSummary[];
  page: number;
  page_size: number;
  total_count: number;
  total_pages: number;
}

export interface MissionNotificationItem {
  id: string;
  command_id: string;
  kind: string;
  severity: "information" | "warning" | "critical";
  status: "unread" | "read" | "acknowledged" | "archived";
  created_at: string;
  escalated_at: string | null;
  acknowledged_at: string | null;
  read_at: string | null;
  archived_at: string | null;
  version: number;
}

export interface MissionNotificationPage {
  items: readonly MissionNotificationItem[];
  unread_count: number;
  escalated_count: number;
  page: number;
  page_size: number;
  total_count: number;
  total_pages: number;
}

export type MobileOwnerReviewState = "pending" | "accepted" | "rejected";
export type MobileOwnerReviewDecision = "accept" | "reject";
export type MobileConnectivityState =
  "connected" | "connecting" | "disconnected";

export interface MobileEngineeringConnectivity {
  state: MobileConnectivityState;
  session_id: string | null;
  last_contact_at: string | null;
  heartbeat_at: string | null;
}

export interface MobileOwnerReviewSummary {
  id: string;
  command_id: string;
  execution_id: string;
  ecid: string;
  provider_identifier: string;
  result_status: string;
  result_disposition: string;
  validation_summary: Readonly<Record<string, unknown>>;
  file_boundary: readonly string[];
  state: MobileOwnerReviewState;
  created_at: string;
  decision: MobileOwnerReviewDecision | null;
  decided_at: string | null;
}

export interface MobileOwnerReviewPage {
  items: readonly MobileOwnerReviewSummary[];
  connectivity: MobileEngineeringConnectivity;
  page: number;
  page_size: number;
  total_count: number;
  total_pages: number;
}

export interface MobileWorkstreamSummary {
  command_id: string;
  ecid: string;
  display_name: string;
  repository_key: string;
  expected_branch: string;
  expected_head: string;
  approval_state: string;
  lifecycle_state: string;
  progress_summary: string;
  owner_action_required: boolean;
  next_owner_action: string;
  connection_state: MobileConnectivityState;
  assigned_worker_id: string | null;
  execution_id: string | null;
  offer_or_lease_state: string | null;
  heartbeat_at: string | null;
  review_id: string | null;
  review_state: string | null;
  authorization_id: string | null;
  authorization_status: string | null;
  repository_operation_id: string | null;
  repository_operation_status: string | null;
  failure_classification: string | null;
  resulting_commit_sha: string | null;
  repository_clean: boolean | null;
  owner_attention_required: boolean;
  updated_at: string;
  pipeline_status: MobileWorkstreamPipelineStatus;
  desired_state: "active" | "paused" | "cancelled";
  control_pending: boolean;
  available_actions: readonly MobileWorkstreamAction[];
  runtime_state: MobileWorkstreamRuntimeState;
  runtime_version: number | null;
  acknowledged_action: string | null;
  acknowledged_at: string | null;
  acknowledgement_expires_at: string | null;
  worker_health: string | null;
  progress_percent: number | null;
  current_activity: string | null;
  acknowledgement_latency_ms: number | null;
  execution_latency_ms: number | null;
  validation_latency_ms: number | null;
  deployment_latency_ms: number | null;
  worker_uptime_seconds: number | null;
  reconnect_count: number;
}

export type MobileWorkstreamRuntimeState = MobileWorkstreamPipelineStatus;

export type MobileWorkstreamPipelineStatus =
  | "queued"
  | "acknowledged"
  | "running"
  | "paused"
  | "waiting_for_owner"
  | "validating"
  | "deploying_preview"
  | "completed"
  | "failed"
  | "cancelled"
  | "recovering";

export type MobileWorkstreamAction = "start" | "pause" | "resume" | "cancel";

export interface MobileWorkstreamDetail extends MobileWorkstreamSummary {
  owner_instruction: string;
  requested_code_changes: boolean;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  timeline: readonly { event: string; occurred_at: string }[];
}

export interface MobileWorkstreamActionResult {
  command_id: string;
  action: MobileWorkstreamAction;
  desired_state: "active" | "paused" | "cancelled";
  accepted: boolean;
  message: string;
  updated_at: string;
}

export interface MobileWorkstreamPage {
  items: readonly MobileWorkstreamSummary[];
  connectivity: MobileEngineeringConnectivity;
  page: number;
  page_size: number;
  total_count: number;
  total_pages: number;
}

export type MilestoneStatus =
  | "draft"
  | "planned"
  | "ready"
  | "running"
  | "externally_running"
  | "waiting_review"
  | "waiting_approval"
  | "blocked"
  | "completed"
  | "paused"
  | "cancelled"
  | "skipped"
  | "archived";
export type MilestoneAction =
  | "start"
  | "approve"
  | "reject"
  | "request_revision"
  | "skip"
  | "pause"
  | "resume"
  | "cancel"
  | "archive";
export type OwnerAttentionClass =
  | "owner_action_required"
  | "running"
  | "waiting_on_dependency"
  | "waiting_on_capacity"
  | "waiting_on_external"
  | "informational";

export interface RoadmapItem {
  id: string;
  title: string;
  repository_key: string;
  expected_branch: string;
  expected_head: string;
  status: "active" | "completed" | "archived";
  version: number;
  created_at: string;
  updated_at: string;
}

export interface MilestoneItem {
  id: string;
  roadmap_id: string;
  position: number;
  title: string;
  objective: string;
  owning_workstream: string;
  owning_branch: string;
  authority: readonly string[];
  constraints: readonly string[];
  dependencies: readonly string[];
  validation: readonly string[];
  deliverables: readonly string[];
  stop_conditions: readonly string[];
  expected_completion_evidence: readonly string[];
  status: MilestoneStatus;
  definition_approved: boolean;
  requested_code_changes: boolean;
  externally_adoptable: boolean;
  attention_class: OwnerAttentionClass;
  attention_reason: string;
  available_owner_actions: readonly MilestoneAction[];
  estimated_start_at: string | null;
  worker_capacity_summary: string | null;
  queue_position: number | null;
  external_evidence: string | null;
  external_adoption: ExternalAdoptionItem | null;
  command_id: string | null;
  version: number;
  started_at: string | null;
  completed_at: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ExternalAdoptionItem {
  id: string;
  repository_key: string;
  branch: string;
  starting_head: string;
  current_head: string;
  worktree_identity: string | null;
  owning_external_workstream: string;
  status:
    | "pending_start"
    | "externally_running"
    | "externally_validating"
    | "externally_blocked"
    | "waiting_review"
    | "revision_requested"
    | "completed"
    | "cancelled"
    | "archived";
  progress_percent: number;
  current_activity: string | null;
  last_evidence_at: string | null;
  responsible_source: string;
  adopted_at: string;
  version: number;
  mission_control_dispatched: false;
  validation_summary: readonly string[];
  blockers: readonly string[];
  evidence_stale: boolean;
  next_owner_action: string;
}

export interface RoadmapPage {
  roadmaps: readonly RoadmapItem[];
  milestones: readonly MilestoneItem[];
  waiting_for_me: readonly MilestoneItem[];
  owner_attention: readonly MilestoneItem[];
  running_milestones: readonly MilestoneItem[];
  dependency_waiting_milestones: readonly MilestoneItem[];
  capacity_waiting_milestones: readonly MilestoneItem[];
  external_work_milestones: readonly MilestoneItem[];
  completed_recently: readonly MilestoneItem[];
  current_milestones: readonly MilestoneItem[];
  next_approved_milestones: readonly MilestoneItem[];
  future_milestones: readonly MilestoneItem[];
  completed_milestones: readonly MilestoneItem[];
  blocked_milestones: readonly MilestoneItem[];
  actionable_count: number;
  projection_warnings?: readonly string[];
}

export interface MobileReviewQuery {
  page: number;
  pageSize: number;
}

export interface MobileReviewApproval {
  expected_version: number;
  instruction_digest: string;
  request_digest: string;
  repository_key: string;
  expected_branch: string;
  expected_head: string;
  requested_code_changes: boolean;
}

export interface MobileReviewCancellation {
  expected_version: number;
  reason_code: MobileCancellationReason;
}

export interface CapacityPolicy {
  id: string;
  maximum_concurrent_workstreams: number;
  maximum_per_worker: number;
  reserved_capacity: number;
  auto_allocate_released_capacity: boolean;
  version: number;
  updated_at: string;
}

export interface WorkerCapacity {
  id: string;
  worker_id: string;
  machine_id: string;
  machine_label: string;
  configured_limit: number;
  allocated_capacity: number;
  reserved_capacity: number;
  available_capacity: number;
  operational_state: string;
  health_state: string;
  last_reconciled_at: string | null;
  version: number;
}

export interface EligibleCapacityWorker {
  worker_id: string;
  worker_name: string;
  provider_identifier: string;
  lifecycle_state: string;
  identity_name: string;
  identity_state: string;
  last_heartbeat_at: string | null;
  health_state: string;
  capacity_configured: boolean;
}

export interface CapacityMachine {
  id: string;
  machine_label: string;
  expected_available_on: string | null;
  enrollment_state: string;
  worker_id: string | null;
}

export interface CapacityReservation {
  id: string;
  command_id: string;
  worker_capacity_id: string;
  machine_label: string;
  ecid: string | null;
  milestone_title: string | null;
  milestone_position: number | null;
  workstream: string | null;
  owning_branch: string | null;
  status: string;
  version: number;
  owner_intent_reference: string;
}

export interface CapacityAllocation {
  id: string;
  command_id: string;
  worker_capacity_id: string;
  machine_label: string;
  ecid: string | null;
  milestone_title: string | null;
  milestone_position: number | null;
  workstream: string | null;
  owning_branch: string | null;
  status: string;
  version: number;
}

export interface CapacityQueueItem {
  command_id: string;
  ecid: string;
  repository_key: string;
  expected_branch: string;
  milestone_id: string | null;
  milestone_title: string | null;
  milestone_position: number | null;
  workstream: string | null;
  roadmap_title: string | null;
  owning_branch: string | null;
  identity_state: "resolved" | "reconciliation_required";
  assigned_worker_id: string | null;
  assigned_worker_name: string | null;
  machine_label: string | null;
  capacity_amount: number;
  requested_at: string;
  decision: string;
  reason: string;
}

export interface CapacitySummary {
  policy: CapacityPolicy | null;
  configured_capacity: number;
  allocated_capacity: number;
  reserved_capacity: number;
  available_capacity: number;
  offline_workers: number;
  unhealthy_workers: number;
  reconciliation_required: number;
  workers: readonly WorkerCapacity[];
  eligible_workers: readonly EligibleCapacityWorker[];
  machines: readonly CapacityMachine[];
  active_reservations: readonly CapacityReservation[];
  active_allocations: readonly CapacityAllocation[];
  waiting_workstreams: readonly CapacityQueueItem[];
}
