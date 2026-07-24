export type EngineeringApprovalState =
  | "awaiting_approval"
  | "approved"
  | "rejected"
  | "canceled"
  | "expired";
export type EngineeringExecutionState = "execution_not_connected";
export type EngineeringCancellationReason =
  | "owner_requested"
  | "scope_changed"
  | "no_longer_needed";

export interface EngineeringCommandSummary {
  id: string;
  ecid: string;
  command_type: string;
  repository_key: string;
  expected_branch: string;
  expected_head: string;
  requested_code_changes: boolean;
  approval_state: EngineeringApprovalState;
  execution_state: EngineeringExecutionState;
  created_at: string;
  expires_at: string;
  version: number;
}

export interface EngineeringCommandDetail extends EngineeringCommandSummary {
  owner_instruction: string;
  instruction_digest: string;
  request_digest: string;
  updated_at: string;
  approved_at: string | null;
  approved_by_user_id: string | null;
  canceled_at: string | null;
  canceled_by_user_id: string | null;
  cancellation_reason_code: string | null;
}

export interface EngineeringCommandPage {
  items: EngineeringCommandSummary[];
  page: number;
  page_size: number;
  total_count: number;
  total_pages: number;
}

export interface EngineeringCommandListQuery {
  approvalState?: EngineeringApprovalState;
  page: number;
  pageSize: number;
}

export interface EngineeringCommandApproveInput {
  expected_version: number;
  instruction_digest: string;
  request_digest: string;
  repository_key: string;
  expected_branch: string;
  expected_head: string;
  requested_code_changes: boolean;
}

export interface EngineeringCommandCancelInput {
  expected_version: number;
  reason_code: EngineeringCancellationReason;
}
