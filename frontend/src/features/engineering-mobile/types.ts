export type MobileReviewState =
  | "awaiting_approval"
  | "approved"
  | "rejected"
  | "canceled"
  | "expired";

export type MobileExecutionState = "execution_not_connected";

export type MobileCancellationReason =
  | "owner_requested"
  | "scope_changed"
  | "no_longer_needed";

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

export type MobileOwnerReviewState = "pending" | "accepted" | "rejected";
export type MobileOwnerReviewDecision = "accept" | "reject";
export type MobileConnectivityState =
  | "connected"
  | "connecting"
  | "disconnected";

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
}

export interface MobileWorkstreamPage {
  items: readonly MobileWorkstreamSummary[];
  connectivity: MobileEngineeringConnectivity;
  page: number;
  page_size: number;
  total_count: number;
  total_pages: number;
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
  status: string;
  version: number;
  owner_intent_reference: string;
}

export interface CapacityAllocation {
  id: string;
  command_id: string;
  worker_capacity_id: string;
  machine_label: string;
  status: string;
  version: number;
}

export interface CapacityQueueItem {
  command_id: string;
  ecid: string;
  repository_key: string;
  expected_branch: string;
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
  machines: readonly CapacityMachine[];
  active_reservations: readonly CapacityReservation[];
  active_allocations: readonly CapacityAllocation[];
  waiting_workstreams: readonly CapacityQueueItem[];
}
