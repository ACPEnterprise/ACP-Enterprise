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
  execution_connected: false;
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
