export type EngineeringReviewState = "pending" | "accepted" | "rejected";
export type EngineeringReviewDecision = "accept" | "reject";
export type RepositoryAuthorizationState =
  | "authorized"
  | "expired"
  | "revoked"
  | "consumed";
export type RepositoryOperationState =
  | "requested"
  | "reserved"
  | "executing"
  | "succeeded"
  | "failed"
  | "reconciliation_required";

export interface EngineeringReviewSummary {
  id: string;
  command_id: string;
  execution_id: string;
  provider_identifier: string;
  review_digest: string;
  state: EngineeringReviewState;
  version: number;
  created_at: string;
  updated_at: string;
  decided_at: string | null;
}

export interface EngineeringReviewDecisionRecord {
  id: string;
  reviewer_user_id: string;
  decision: EngineeringReviewDecision;
  review_digest: string;
  reason_code: string | null;
  decided_at: string;
}

export interface EngineeringReviewPackage {
  review: EngineeringReviewSummary;
  ecid: string;
  command_type: string;
  owner_instruction: string;
  requested_code_changes: boolean;
  repository_key: string;
  expected_branch: string;
  expected_head: string;
  result_status: string;
  result_disposition: string;
  evidence_summary: Readonly<Record<string, unknown>>;
  validation_summary: Readonly<Record<string, unknown>>;
  output_references: readonly string[];
  failure_classification: string | null;
  repository_mutated: false;
  result_received_at: string;
  decision: EngineeringReviewDecisionRecord | null;
}

export interface EngineeringReviewDecisionInput {
  expected_version: number;
  review_digest: string;
  decision: EngineeringReviewDecision;
  reason_code: string | null;
}

export interface RepositoryAuthorizationInput {
  review_id: string;
  review_digest: string;
  operation_type: "create_commit";
  file_boundary: readonly string[];
  expected_branch: string;
  expected_base_commit: string;
  expires_at: string;
  idempotency_key: string;
}

export interface RepositoryAuthorizationDetail {
  id: string;
  command_id: string;
  review_id: string;
  operation_type: "create_commit";
  expected_branch: string;
  expected_base_commit: string;
  state: RepositoryAuthorizationState;
  version: number;
  authorized_at: string;
  expires_at: string;
  revoked_at: string | null;
  consumed_at: string | null;
  capability_id: string;
  execution_id: string;
  result_id: string;
  review_decision_id: string;
  file_boundary: readonly string[];
  review_digest: string;
  authorization_digest: string;
  authorization_eligible: boolean;
}

export interface ExecuteRepositoryCommitInput {
  authorization_id: string;
  capability_id: string;
  authorization_digest: string;
  commit_subject: string;
  idempotency_key: string;
}

export interface RepositoryOperationDetail {
  id: string;
  authorization_id: string;
  command_id: string;
  operation_type: "create_commit";
  commit_subject: string;
  expected_branch: string;
  expected_base_commit: string;
  state: RepositoryOperationState;
  resulting_commit_sha: string | null;
  failure_classification: string | null;
  version: number;
  requested_at: string;
  reserved_at: string | null;
  execution_started_at: string | null;
  succeeded_at: string | null;
  failed_at: string | null;
  reconciliation_required_at: string | null;
  execution_id: string;
  review_decision_id: string;
  file_boundary: readonly string[];
  failure_detail: string | null;
  owner_attention_required: boolean;
}
