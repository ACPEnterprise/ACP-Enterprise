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
