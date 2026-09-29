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

export async function getGoogleAdsOwnerWorkspace() {
  const [readiness, bindings, sync, coverage, reconciliation] = await Promise.all([
    apiClient.get<GoogleAdsConnectionReadiness>("/api/v1/marketing/google-ads/connection-readiness"),
    apiClient.get<GoogleAdsAccountBinding[]>("/api/v1/marketing/google-ads/account-bindings"),
    apiClient.get<GoogleAdsSyncStatus[]>("/api/v1/marketing/google-ads/sync-status"),
    apiClient.get<GoogleAdsCoverage[]>("/api/v1/marketing/google-ads/coverage"),
    apiClient.get<GoogleAdsReconciliationFinding[]>("/api/v1/marketing/google-ads/reconciliation"),
  ]);
  return {
    readiness: readiness.data,
    bindings: bindings.data,
    sync: sync.data,
    coverage: coverage.data,
    reconciliation: reconciliation.data,
  };
}
