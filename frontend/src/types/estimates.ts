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
