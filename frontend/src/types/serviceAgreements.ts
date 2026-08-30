export interface AgreementPlan {
  id: string;
  company_id: string;
  branch_id?: string;
  code: string;
  name: string;
  version: number;
  status: string;
  currency: string;
  price_amount?: string;
  billing_cadence: string;
  duration_months: number;
  included_visits: number;
  benefits: Record<string, unknown>[];
  definition_digest: string;
  activated_at?: string;
  created_at: string;
}
export interface ServiceAgreement {
  id: string;
  company_id: string;
  branch_id: string;
  customer_id: string;
  plan_id: string;
  agreement_number: string;
  status: string;
  start_date: string;
  end_date: string;
  plan_snapshot: Record<string, unknown>;
  evidence_digest: string;
  version: number;
  cancellation_reason?: string;
  created_at: string;
  updated_at: string;
}
export interface ServiceEntitlement {
  id: string;
  agreement_id: string;
  service_location_id: string;
  sequence: number;
  service_category: string;
  eligible_from: string;
  eligible_to: string;
  status: string;
  source_digest: string;
}
export interface AgreementWorkspace {
  agreements: ServiceAgreement[];
  entitlements: ServiceEntitlement[];
  active_count: number;
  renewal_pending_count: number;
  service_due_count: number;
  billing_unconfigured_count: number;
}
