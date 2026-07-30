export type ProjectionAvailability =
  | "available"
  | "unavailable"
  | "not_applicable";

export type ExecutionMonitoringState =
  | "not_approved"
  | "approved_not_dispatchable"
  | "disconnected"
  | "queued"
  | "starting"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export interface ExecutionTimelineEntry {
  event: string;
  occurred_at: string;
}

export interface ExecutionLeaseStatus {
  availability: ProjectionAvailability;
  worker_id: string | null;
  status: string | null;
  started_at: string | null;
  expires_at: string | null;
  released_at: string | null;
  phase: "active" | "expiring" | "inactive";
}

export interface ExecutionHeartbeatStatus {
  availability: ProjectionAvailability;
  health: string | null;
  last_seen: string | null;
  age_seconds: number | null;
}

export interface TransportSessionStatus {
  availability: ProjectionAvailability;
  state: string | null;
  established_at: string | null;
  expires_at: string | null;
  last_contact_at: string | null;
}

export interface ExecutionResultStatus {
  availability: ProjectionAvailability;
  status: string | null;
  validation_available: boolean;
  evidence_available: boolean;
  output_reference_count: number;
  failure_classification: string | null;
  created_at: string | null;
}

export interface MobileExecutionStatus {
  command_id: string;
  ecid: string;
  approval_state: string;
  monitoring_state: ExecutionMonitoringState;
  execution_available: boolean;
  execution_connected: boolean;
  connection_state: "connected" | "connecting" | "disconnected";
  transport_health: string;
  execution_id: string | null;
  execution_state: string | null;
  execution_status: string | null;
  progress_label: string;
  requested_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
  lease: ExecutionLeaseStatus;
  heartbeat: ExecutionHeartbeatStatus;
  transport_session: TransportSessionStatus;
  result: ExecutionResultStatus;
  review_available: boolean;
  review_id: string | null;
  review_state: "pending" | "accepted" | "rejected" | null;
  review_version: number | null;
  review_decided_at: string | null;
  authorization_required: boolean;
  authorization_status: string | null;
  authorization_id: string | null;
  authorized_at: string | null;
  authorization_expires_at: string | null;
  authorization_revoked_at: string | null;
  authorization_consumed_at: string | null;
  authorized_operation_type: string | null;
  authorization_eligible: boolean;
  repository_operation_required: boolean;
  repository_operation_id: string | null;
  repository_operation_type: string | null;
  repository_operation_status: string | null;
  repository_operation_eligible: boolean;
  repository_operation_expected_branch: string | null;
  repository_operation_resulting_commit_sha: string | null;
  repository_operation_requested_at: string | null;
  repository_operation_reserved_at: string | null;
  repository_operation_started_at: string | null;
  repository_operation_completed_at: string | null;
  repository_operation_failed_at: string | null;
  repository_operation_reconciliation_at: string | null;
  repository_operation_failure_classification: string | null;
  repository_operation_owner_attention_required: boolean;
  timeline: readonly ExecutionTimelineEntry[];
  terminal: boolean;
  polling_after_seconds: number | null;
}

export interface ExecutionStatusStream {
  subscribe(
    commandId: string,
    onStatus: (status: MobileExecutionStatus) => void,
  ): () => void;
}
