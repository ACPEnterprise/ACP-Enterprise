export interface PriceBookCategory {
  id: string;
  company_id: string;
  parent_id: string | null;
  code: string;
  name: string;
  description: string | null;
  position: number | null;
  status: string;
  version: number;
}
export interface TaxClassification {
  id: string;
  company_id: string;
  code: string;
  name: string;
  taxable: boolean;
  status: string;
  version: number;
}
export interface PriceBookServiceItem {
  id: string;
  company_id: string;
  branch_id: string | null;
  category_id: string;
  code: string;
  name: string;
  customer_description: string;
  internal_description: string | null;
  status: string;
  current_version_id: string | null;
  version: number;
}
export interface PriceBookComponent {
  id: string;
  component_type: "labor" | "material" | "other_direct";
  code: string | null;
  label: string;
  quantity: string;
  unit_cost?: string;
  extended_cost?: string;
  position: number;
}
export interface PriceBookVersion {
  id: string;
  company_id: string;
  service_item_id: string;
  branch_id: string | null;
  tax_classification_id: string;
  revision: number;
  currency: string;
  unit_price: string;
  effective_at: string;
  expires_at: string | null;
  status: string;
  rounding_mode: string;
  version: number;
  components: PriceBookComponent[];
  cost_readiness: "COST_COMPLETE" | "INSUFFICIENT_COST_EVIDENCE";
  expected_direct_cost?: string;
  expected_direct_contribution?: string;
}
export interface PriceBookOptionGroup {
  id: string;
  company_id: string;
  code: string;
  name: string;
  minimum_selections: number;
  maximum_selections: number;
  status: string;
}
export interface PriceBookOption {
  id: string;
  company_id: string;
  option_group_id: string;
  service_item_id: string;
  label: string;
  position: number;
}
export interface PriceBookCatalog {
  categories: PriceBookCategory[];
  tax_classifications: TaxClassification[];
  service_items: PriceBookServiceItem[];
  versions: PriceBookVersion[];
  option_groups: PriceBookOptionGroup[];
  options: PriceBookOption[];
  total_service_items: number;
  limit: number;
  offset: number;
  costs_visible: boolean;
}

export interface PriceBookCandidateReviewItem {
  candidate_identity: string;
  native_service_item_id: string | null;
  service_code: string;
  name: string;
  customer_description: string;
  category: string;
  admission_status: "admitted" | "held";
  review_flags: string[];
  activation_blockers: string[];
  candidate_prices: Record<string, string | null>;
  price_derivation: string;
  labor_hours?: string;
  material_cost_evidence?: string;
  source_sheet: string;
  source_row: number;
  source_digest: string;
  evidence_digest: string;
  tax_decision_group: string;
  conflict_reason: string | null;
}

export interface PriceBookCandidateReviewPage {
  items: PriceBookCandidateReviewItem[];
  counts: Record<string, number>;
  total: number;
  limit: number;
  offset: number;
  costs_visible: boolean;
}

export interface PriceBookActivationReadiness {
  price_version_id: string;
  draft_version: number;
  candidate_identity: string;
  service_code: string;
  price_approved: boolean;
  tax_approved: boolean;
  effective_date_approved: boolean;
  activation_authorized: boolean;
  material_mapping_required: boolean;
  source_conflict: boolean;
  activation_ready: boolean;
  remaining_blockers: string[];
  rationale: Record<string, string>;
}
export interface CompanyTaxPolicy {
  id: string;
  company_id: string;
  policy_identity: string;
  version: number;
  status: "draft" | "certified" | "superseded";
  effective_at: string;
  expires_at: string | null;
  customer_service_treatment: "NOT_TAXED" | "TAXED" | "REVIEW_REQUIRED";
  customer_material_treatment: "NOT_TAXED" | "TAXED" | "REVIEW_REQUIRED";
  purchase_material_tax_handling:
    "PAID_AT_PURCHASE" | "EXEMPT" | "REVIEW_REQUIRED";
  authority_source: string;
  authority_notes: string | null;
  authorized_exceptions: Array<Record<string, unknown>>;
  supersedes_policy_id: string | null;
  certified_by_user_id: string | null;
  certified_at: string | null;
  created_at: string;
}
export interface CompanyTaxPolicyPage {
  current: CompanyTaxPolicy | null;
  history: CompanyTaxPolicy[];
}
export interface PriceBookAuditItem {
  id: string;
  action: string;
  reason: string;
  actor_user_id: string;
  occurred_at: string;
}

export interface PriceBookSnapshot {
  id: string;
  company_id: string;
  branch_id: string;
  service_item_id: string;
  price_version_id: string;
  quantity: string;
  unit_price: string;
  extended_amount: string;
  currency: string;
  snapshot_data: Record<string, unknown>;
}
export interface PriceBookReviewBatch {
  id: string;
  configuration_version: string;
  review_type: string;
  selector: Record<string, unknown>;
  service_codes: string[];
  exclusions: string[];
  candidate_set_digest: string;
  status: string;
  decision_reason: string | null;
  version: number;
}
export interface PriceBookAdjustmentProposal {
  id: string;
  source_price_book_version: string;
  recommendation_identity: string;
  affected_service_codes: string[];
  owner_exclusions: string[];
  transformation_kind: string;
  transformation: Record<string, unknown>;
  impacts: Array<Record<string, unknown>>;
  limitations: string[];
  effective_at: string;
  proposal_digest: string;
  status: string;
  version: number;
}
export interface PriceBookBulkMaterialization {
  proposal_id: string;
  proposal_digest: string;
  created_version_ids: string[];
  created_count: number;
  replayed: boolean;
}
