export type InvoiceStatus =
  | "draft"
  | "cancelled"
  | "issued"
  | "partially_paid"
  | "adjusted"
  | "paid"
  | "voided";

export interface Invoice {
  id: string;
  company_id: string;
  branch_id: string;
  customer_id: string;
  service_location_id: string;
  job_id: string;
  estimate_id?: string;
  estimate_revision_id?: string;
  invoice_number: string;
  status: InvoiceStatus;
  accounting_status:
    "pending" | "posted" | "reversed" | "reconciliation_required";
  currency: string;
  issue_date: string;
  due_date: string;
  terms: string;
  subtotal_amount: string;
  discount_amount: string;
  taxable_basis?: string;
  tax_amount: string;
  total_amount: string;
  open_amount: string;
  calculation_digest: string;
  legacy_evidence_missing: boolean;
  version: number;
  issued_at?: string;
  created_at: string;
  updated_at: string;
}

export interface CreateInvoiceInput {
  branch_id: string;
  estimate_id: string;
  job_id: string;
  due_date: string;
  terms: string;
  idempotency_key: string;
}

export interface InvoiceMutationInput {
  branch_id: string;
  expected_version: number;
  idempotency_key: string;
  occurred_at: string;
}

export type InvoiceWorkspaceState = "all" | "open" | "overdue" | "needs_attention" | InvoiceStatus;

export interface InvoiceWorkspaceItem {
  id: string;
  branch_id: string;
  customer_id: string;
  customer_number: string;
  customer_display_name: string;
  service_location_id: string;
  service_location_label: string;
  job_id: string;
  job_number: string;
  estimate_id?: string;
  invoice_number: string;
  status: InvoiceStatus;
  accounting_status: Invoice["accounting_status"];
  currency: string;
  issue_date: string;
  due_date: string;
  terms: string;
  total_amount: string;
  open_amount: string;
  age_days: number;
  aging_bucket: "paid" | "current" | "1_30" | "31_60" | "61_90" | "91_plus";
  attention_reasons: string[];
  last_ar_activity_type?: string;
  last_ar_activity_at?: string;
  legacy_evidence_missing: boolean;
  version: number;
}

export interface InvoiceWorkspaceFilters {
  asOf: string;
  state: InvoiceWorkspaceState;
  query?: string;
  customerId?: string;
  branchId?: string;
  limit?: number;
  offset?: number;
}

export interface CustomerBalance {
  customer_id: string;
  customer_number: string;
  customer_display_name: string;
  currency: string;
  invoice_total: string;
  open_balance: string;
  credit_total: string;
  write_off_total: string;
  applied_payment_total: string;
  unapplied_receipt_total: string;
  disputed_receipt_total: string;
  native_invoice_count: number;
  legacy_evidence_incomplete: boolean;
  as_of: string;
}
