export interface EstimateLine {
  id: string;
  title: string;
  description: string | null;
  snapshot_id: string;
  snapshot_digest: string;
  quantity: string;
  unit_price: string;
  line_total: string;
  currency: string;
  option_group_id: string | null;
  option_id: string | null;
  discount_allocation: string;
  discounted_basis: string;
  tax_amount: string;
  taxable: boolean;
}

export interface EstimateRevision {
  id: string;
  revision_number: number;
  proposal_title: string;
  customer_message: string | null;
  terms: string | null;
  currency: string;
  subtotal_amount: string;
  discount_type: "fixed" | "percentage" | null;
  discount_value: string | null;
  discount_amount: string;
  taxable_basis: string;
  tax_amount: string;
  total_amount: string;
  lines: EstimateLine[];
}

export interface Estimate {
  id: string;
  branch_id: string;
  customer_id: string;
  estimate_number: string;
  status: string;
  acceptance_status: string;
  version: number;
  current_revision: EstimateRevision;
}

export interface EstimateProposalInput {
  branch_id: string;
  customer_id: string;
  service_location_id?: string;
  proposal_title: string;
  customer_message?: string;
  terms?: string;
  lines: Array<{ snapshot_id: string; title: string; description?: string }>;
  discount_type?: "fixed" | "percentage";
  discount_value?: string;
}

export interface EstimateTransitionInput {
  branch_id: string;
  expected_version: number;
  occurred_at: string;
}

export interface EstimateDecisionInput extends EstimateTransitionInput {
  customer_name: string;
  customer_email?: string;
  customer_comment?: string;
  rejection_reason?: string;
  evidence_reference?: string;
}

export interface EstimateSummary {
  id: string;
  branch_id: string;
  customer_id: string;
  service_location_id: string | null;
  estimate_number: string;
  status: string;
  acceptance_status: string;
  version: number;
  proposal_title: string;
  currency: string;
  total_amount: string;
  expires_at: string | null;
  updated_at: string;
}

export interface EstimateList {
  items: EstimateSummary[];
  total: number;
}

export interface EstimateArtifact {
  schema_version: number;
  template_version: string;
  estimate_id: string;
  estimate_version: number;
  revision_id: string;
  revision_number: number;
  status: string;
  artifact_digest: string;
  filename: string;
  media_type: "text/html";
  content: string;
}
export interface CommercialPolicy {
  id: string; company_id: string; branch_id: string; policy_type: string;
  status: "unconfigured" | "draft" | "active" | "inactive";
  configuration: Record<string, unknown>; readiness_reason: string; version: number;
  evidence_digest: string; created_by_user_id: string; created_at: string;
}
export interface CommercialPolicyWrite {
  branch_id: string; policy_type: string; status: CommercialPolicy["status"];
  configuration: Record<string, unknown>; readiness_reason: string;
  expected_version?: number; idempotency_key: string;
}
export interface EstimateFollowUp {
  id: string; branch_id: string; estimate_id: string; revision_id: string;
  assigned_user_id: string; state: "open" | "snoozed" | "completed" | "canceled";
  due_at: string | null; disposition: string | null; sequence: number;
  evidence_digest: string; occurred_at: string;
}
export interface EstimateFollowUpWrite {
  branch_id: string; assigned_user_id: string; state: EstimateFollowUp["state"];
  due_at?: string; disposition?: string; occurred_at: string; idempotency_key: string;
}
export interface PresentationCredential {
  id: string; estimate_id: string; revision_id: string; revision_number: number; estimate_version: number;
  artifact_digest: string; recipient_reference: string; channel: string; status: string;
  expires_at: string | null; evidence_digest: string; created_at: string;
  viewed_at: string | null; access_token: string;
}
export interface CommercialReport {
  created: number; presented: number; viewed: number; accepted: number; rejected: number;
  expired: number; accepted_not_converted: number; converted: number;
  accepted_value_by_currency: Record<string, string>;
  outstanding_value_by_currency: Record<string, string>;
}
export interface CommercialHistoryItem { evidence_type: string; state: string; occurred_at: string; actor_reference: string | null; revision_id: string | null; evidence_digest: string | null; detail: string | null }
