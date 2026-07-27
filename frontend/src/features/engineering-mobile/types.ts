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
