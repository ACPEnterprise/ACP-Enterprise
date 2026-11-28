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
  contract: "hcp-customer-source-history/v3";
  authority: "HCP_SOURCE_BACKED_OPERATIONAL_HISTORY";
  accepted_as_acp_accounting: false;
  mutation_authority: "none";
  source_customer_id: string;
  source_manifest_sha256: string;
  counts: {
    locations: number;
    jobs: number;
    appointments: number;
    estimates: number;
    invoices: number;
    payments: number;
    refunds: number;
  };
  locations: Array<{
    source_id: string;
    address: string | null;
    city: string | null;
    state: string | null;
    postal_code: string | null;
    authority: "HCP_SOURCE_BACKED_OPERATIONAL_HISTORY";
  }>;
  jobs: Array<{
    source_id: string;
    source_location_id: string | null;
    number: string | null;
    status: string | null;
    created_at: string | null;
    updated_at: string | null;
    scheduled_start: string | null;
    scheduled_end: string | null;
    service_date: string | null;
    source_location: {
      address: string | null;
      city: string | null;
      state: string | null;
      postal_code: string | null;
    } | null;
    description: string | null;
    notes: Array<{ source_id: string | null; content: string | null }>;
    work_timestamps: {
      started_at?: string | null;
      completed_at?: string | null;
      on_my_way_at?: string | null;
    };
    original_estimate_id: string | null;
    original_estimate_ids: string[];
    invoice_number: string | null;
    total_amount: number | string | null;
    outstanding_balance: number | string | null;
    assigned_employee_source_ids: string[];
    assigned_employee_names: string[];
    attachments: Array<{
      source_id: string;
      file_name: string | null;
      file_type: string | null;
      size_bytes: number | null;
      content_sha256: string | null;
      status: string | null;
      body_available: boolean;
      conflict_reason: string | null;
      view_url: string | null;
    }>;
    authority: "HCP_SOURCE_BACKED_OPERATIONAL_HISTORY";
  }>;
  appointments: Array<{
    source_id: string;
    source_job_id: string | null;
    scheduled_start: string | null;
    scheduled_end: string | null;
    assigned_employee_source_ids: string[];
    authority: "HCP_SOURCE_BACKED_OPERATIONAL_HISTORY";
  }>;
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
    line_items: Array<{
      description: string | null;
      amount_cents: number | null;
    }>;
    payments: HcpSourcePayment[];
    refunds: Array<{
      source_id: string | null;
      status: string;
      amount_cents: number;
      date: string | null;
      payment_method: string | null;
      identity_disposition: "EXACT_PROVIDER_REFUND_ID" | "SOURCE_BACKED_UNLINKED_REFUND";
      aggregation_safe: false;
      authority: "HCP_SOURCE_BACKED_REFUND_EVIDENCE_NOT_ACCOUNTING_POSTING";
    }>;
    authority: "HCP_SOURCE_BACKED_OPERATIONAL_HISTORY";
  }>;
};

export type HcpHistoricalCustomerSearch = {
  contract: "hcp-customer-source-search/v1";
  authority: "HCP_SOURCE_BACKED_HISTORICAL_CUSTOMER";
  mutation_authority: "none";
  query: string;
  items: Array<{
    source_customer_id: string;
    native_customer_id?: string | null;
    display_name: string;
    primary_location: string | null;
    authority: "HCP_SOURCE_BACKED_HISTORICAL_CUSTOMER";
    accepted_as_native: false;
  }>;
  match_count: number;
  offset: number;
  limit: number;
  limited: boolean;
  source_manifest_sha256: string;
};
