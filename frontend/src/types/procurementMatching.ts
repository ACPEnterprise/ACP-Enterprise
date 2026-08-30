export type ProcurementMatchLine = {
  id: string;
  purchase_order_line_id: string;
  receipt_line_id: string | null;
  bill_line_id: string;
  ordered_quantity: string;
  received_quantity: string;
  returned_quantity: string;
  net_accepted_quantity: string;
  billed_quantity: string;
  po_unit_cost: string;
  billed_unit_cost: string;
  quantity_variance: string;
  price_variance: string;
  state: string;
  evidence_digest: string;
};

export type ProcurementMatchException = {
  id: string;
  match_line_id: string | null;
  category: string;
  status: string;
  expected_evidence: string;
  actual_evidence: string;
  resolution: string | null;
  resolution_note: string | null;
  version: number;
};

export type ProcurementMatch = {
  id: string;
  company_id: string;
  branch_id: string;
  purchase_order_id: string;
  vendor_bill_id: string;
  state: string;
  admission_state: string;
  policy_reference: string | null;
  purchase_order_version: number;
  bill_version: number;
  source_evidence_digest: string;
  evaluation_sequence: number;
  supersedes_match_id: string | null;
  superseded_at: string | null;
  evidence_digest: string;
  evaluated_by_user_id: string;
  evaluated_at: string;
  version: number;
  lines: ProcurementMatchLine[];
  exceptions: ProcurementMatchException[];
};

export type EvaluateProcurementMatchInput = {
  purchase_order_id: string;
  vendor_bill_id: string;
  expected_purchase_order_version: number;
  expected_bill_version: number;
  idempotency_key: string;
};

export type ProcurementMatchCandidate = {
  vendor_bill_id: string;
  vendor_bill_number: string;
  vendor_bill_version: number;
  branch_id: string;
  accounting_vendor_id: string;
  purchase_order_id: string | null;
  purchase_order_number: string | null;
  purchase_order_version: number | null;
  linkage_state: string;
  active_match_id: string | null;
  active_match_state: string | null;
  active_admission_state: string | null;
  active_evaluation_sequence: number | null;
  active_match_current: boolean;
};

export type ResolveProcurementMatchInput = {
  matchId: string;
  exceptionId: string;
  expected_match_version: number;
  expected_exception_version: number;
  resolution: string;
  note: string;
  idempotency_key: string;
};

export type VendorPerformanceReport = {
  definition_version: number;
  company_id: string;
  branch_id: string | null;
  evaluated_at: string;
  evidence_digest: string;
  items: Array<{
    vendor_id: string;
    purchase_order_count: number;
    ordered_quantity: string;
    accepted_received_quantity: string;
    returned_quantity: string;
    net_accepted_quantity: string;
    fulfillment_ratio: string | null;
    return_ratio: string | null;
    completed_lead_time_samples: number;
    average_lead_time_days: string | null;
    discrepancy_count: number;
    price_variance_line_count: number;
    evidence_digest: string;
  }>;
};
