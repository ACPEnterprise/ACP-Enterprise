import { apiClient } from "./client";

export interface GoogleAdsConnectionReadiness {
  connection_status: "not_configured" | "configuration_required" | "ready_to_connect" | "connected" | "revoked_or_error";
  environment: string;
  oauth_client_configured: boolean;
  callback_configured: boolean;
  developer_token_configured: boolean;
  environment_safe_secret_custody: boolean;
  live_ingestion_enabled: boolean;
  authorization_available: boolean;
  granted_scopes: string[];
  connected_at: string | null;
  bound_account_count: number;
  blockers: string[];
}

export interface GoogleAdsAccountBinding {
  id: string;
  branch_id: string;
  provider_account_id: string;
  external_customer_id: string;
  descriptive_name: string;
  currency_code: string | null;
  time_zone: string | null;
  ingestion_enabled: boolean;
  bound_at: string;
}

export interface GoogleAdsSyncStatus {
  provider_account_id: string;
  status: string;
  requested_start_at: string | null;
  requested_end_at: string | null;
  record_count: number;
  exception_count: number;
  completed_at: string | null;
}

export interface GoogleAdsCoverage {
  provider_account_id: string;
  interval_start: string;
  interval_end: string;
  as_of: string;
  attribution_policy_version: string;
  evidence_count: number;
  coverage_percent: number;
  missing_components: string[];
  availability: string;
}

export interface GoogleAdsReconciliationFinding {
  id: string;
  provider_account_id: string;
  kind: string;
  state: string;
  missing_components: string[];
  observed_at: string;
}

export interface MarketingReadinessProjection {
  projection_version: "marketing-readiness.v1";
  company_id: string;
  provider_family: "google_ads";
  as_of: string;
  owner_state: "CONFIGURATION_REQUIRED" | "READY_TO_AUTHORIZE" | "AUTHORIZED_ACCOUNT_SELECTION_REQUIRED" | "CONNECTED_NOT_INGESTING" | "INGESTING" | "DEGRADED";
  owner_guidance: string[];
  provider_configured: boolean;
  oauth_runtime_ready: boolean;
  secret_custody_ready: boolean;
  connection_state: string;
  account_discovery_state: string;
  account_bound: boolean;
  branch_mappings: { branch_id: string; provider_account_id: string; ingestion_enabled: boolean }[];
  ingestion_enabled: boolean;
  last_successful_sync_at: string | null;
  current_evidence_period: { interval_start: string; interval_end: string; as_of: string } | null;
  spend_evidence_availability: "AVAILABLE" | "PARTIAL" | "UNAVAILABLE" | "STALE";
  spend_evidence_available: boolean;
  campaign_evidence_available: boolean;
  search_term_evidence_available: boolean;
  unresolved_reconciliation_findings: number;
  provider_unavailable: boolean;
  provider_error: boolean;
  missing_components: string[];
}

export async function getGoogleAdsOwnerWorkspace() {
  const [projection, readiness, bindings, sync, coverage, reconciliation] = await Promise.all([
    apiClient.get<MarketingReadinessProjection>("/api/v1/marketing/readiness"),
    apiClient.get<GoogleAdsConnectionReadiness>("/api/v1/marketing/google-ads/connection-readiness"),
    apiClient.get<GoogleAdsAccountBinding[]>("/api/v1/marketing/google-ads/account-bindings"),
    apiClient.get<GoogleAdsSyncStatus[]>("/api/v1/marketing/google-ads/sync-status"),
    apiClient.get<GoogleAdsCoverage[]>("/api/v1/marketing/google-ads/coverage"),
    apiClient.get<GoogleAdsReconciliationFinding[]>("/api/v1/marketing/google-ads/reconciliation"),
  ]);
  return {
    projection: projection.data,
    readiness: readiness.data,
    bindings: bindings.data,
    sync: sync.data,
    coverage: coverage.data,
    reconciliation: reconciliation.data,
  };
}

export async function beginGoogleAdsAuthorization(): Promise<string> {
  const response = await apiClient.post<{ authorization_url: string }>(
    "/api/v1/marketing/google-ads/oauth/authorize",
  );
  return response.data.authorization_url;
}
