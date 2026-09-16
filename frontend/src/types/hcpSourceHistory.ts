export type HcpSourcePayment = {
  source_id: string;
  status: string;
  amount_cents: number;
  date: string | null;
  payment_method: string | null;
  overlap_disposition: "HCP_ONLY_SOURCE_EVIDENCE" | "HOLD_FROM_AGGREGATION_PENDING_QBO_RECONCILIATION";
  authority: "HCP_SOURCE_BACKED_PAYMENT_EVIDENCE_NOT_ACCOUNTING_POSTING";
};

export type HcpCustomerSourceHistory = {
  contract: "hcp-customer-source-history/v1";
  authority: "HCP_SOURCE_BACKED_OPERATIONAL_HISTORY";
  accepted_as_acp_accounting: false;
  mutation_authority: "none";
  source_customer_id: string;
  source_manifest_sha256: string;
  counts: { estimates: number; invoices: number; payments: number };
  estimates: Array<{
    source_id: string;
    number: string | null;
    status: string | null;
    created_at: string | null;
    updated_at: string | null;
    options: Array<{ source_id: string; name: string | null; amount_cents: number | null }>;
    authority: "HCP_SOURCE_BACKED_OPERATIONAL_HISTORY";
  }>;
  invoices: Array<{
    source_id: string;
    source_job_id: string;
    number: string | null;
    status: string | null;
    amount_cents: number | null;
    balance_cents: number | null;
    invoice_date: string | null;
    service_date: string | null;
    payments: HcpSourcePayment[];
    authority: "HCP_SOURCE_BACKED_OPERATIONAL_HISTORY";
  }>;
};
