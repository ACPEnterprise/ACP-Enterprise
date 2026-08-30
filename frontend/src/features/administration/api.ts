import { apiClient } from "../../api/client";

export interface CompanyRole {
  id: string;
  company_id: string;
  code: string;
  name: string;
  description: string | null;
  status: string;
  is_system: boolean;
}

export interface PermissionDefinition {
  id: string;
  code: string;
  name: string;
  description: string | null;
  scope: string;
  active: boolean;
  assignable: boolean;
  assigned: boolean;
  reconciliation_required: boolean;
}

export interface OnboardingRecord {
  id: string;
  user_id: string;
  employee_id: string | null;
  membership_id: string;
  branch_id: string;
  masked_login: string;
  status: "invited" | "activated" | "revoked";
  created_at: string;
}

export interface OnboardingOption { id: string; code: string; name: string }
export interface OnboardingOptions {
  branches: OnboardingOption[];
  roles: OnboardingOption[];
}

export interface OnboardingCreate {
  request_key: string;
  branch_id: string;
  first_name: string;
  last_name: string;
  display_name: string;
  create_employee: boolean;
  employee_type?: "employee" | "contractor" | "vendor";
  employee_number_prefix?: string;
  employee_number_width?: number;
  role_ids: string[];
  login_email: string;
}

const ONBOARDING_PATH = "/api/v1/identity-onboarding";

export async function listOnboarding(): Promise<OnboardingRecord[]> {
  return (await apiClient.get<OnboardingRecord[]>(ONBOARDING_PATH)).data;
}

export async function getOnboardingOptions(): Promise<OnboardingOptions> {
  return (await apiClient.get<OnboardingOptions>(`${ONBOARDING_PATH}/options`)).data;
}

export async function createOnboarding(data: OnboardingCreate): Promise<OnboardingRecord> {
  return (await apiClient.post<OnboardingRecord>(ONBOARDING_PATH, data)).data;
}

export async function revokeOnboarding(id: string): Promise<OnboardingRecord> {
  return (await apiClient.post<OnboardingRecord>(`${ONBOARDING_PATH}/${id}/revoke`)).data;
}

export async function reissueOnboarding(id: string): Promise<OnboardingRecord> {
  return (await apiClient.post<OnboardingRecord>(`${ONBOARDING_PATH}/${id}/reissue`)).data;
}

export async function activateOnboarding(token: string, password: string): Promise<OnboardingRecord> {
  return (await apiClient.post<OnboardingRecord>(`${ONBOARDING_PATH}/activate/complete`, { token, password })).data;
}

const ADMIN_PATH = "/api/v1/company-admin";
const QBO_SANDBOX_AUTHORIZE_PATH = "/api/v1/integrations/qbo/oauth/authorize";
const QBO_SANDBOX_CONNECTION_PATH = "/api/v1/integrations/qbo/connection";
const QBO_SANDBOX_DISCONNECT_PATH = "/api/v1/integrations/qbo/oauth/disconnect";
const MIGRATION_READINESS_PATH = "/api/v1/migration/readiness";

export interface MigrationReadiness {
  overall_status: string;
  current_phase: string;
  authority_digest: string;
  reconciliation_digest: string;
  stale: boolean;
  safe_failure_code: string | null;
  historical_window: {
    starts_on: string | null;
    ends_on: string;
    opening_evidence_state: string;
    completeness: string;
  };
  sources: Array<{
    source: string;
    environment: string;
    status: string;
    connection_state: string;
    acquisition_state: string;
    manifest_state: string;
    delta_state: string;
    freeze_state: string;
    authority_digest: string;
  }>;
  counts: Array<{
    domain: string;
    source: number;
    migrated: number;
    held: number;
    exception: number;
    non_applicable: number;
    deferred: number;
    unresolved: number;
    delta: number;
  }>;
  timeline: Array<{ phase: string; status: string }>;
  authority_states: Array<{ fact: string; state: string }>;
  owner_decisions: Array<{ decision: string; state: string }>;
  run_history: Array<{
    run_id: string;
    source: string;
    state: string;
    reconciliation: string;
    replay: string;
    holds: number;
    exceptions: number;
  }>;
  recovery_state: string;
}

export async function getMigrationReadiness(): Promise<MigrationReadiness> {
  return (await apiClient.get<MigrationReadiness>(MIGRATION_READINESS_PATH))
    .data;
}

export type QboSandboxConnectionState =
  | "connected"
  | "not_connected"
  | "disconnecting"
  | "disconnect_failed"
  | "unavailable";

interface QboSandboxConnectionResponse {
  status: "qbo_sandbox_connection";
  connection_state: QboSandboxConnectionState;
}

interface QboSandboxAuthorizationResponse {
  status: "sandbox_oauth_initiation";
  authorization_url: string;
}

function validatedIntuitAuthorizationUrl(value: string): string {
  const url = new URL(value);
  const expectedCallback = `${window.location.origin}/api/v1/integrations/qbo/oauth/callback`;
  if (
    url.protocol !== "https:" ||
    url.hostname !== "appcenter.intuit.com" ||
    url.pathname !== "/connect/oauth2" ||
    url.username ||
    url.password ||
    url.searchParams.get("response_type") !== "code" ||
    url.searchParams.get("scope") !== "com.intuit.quickbooks.accounting" ||
    url.searchParams.get("redirect_uri") !== expectedCallback ||
    !url.searchParams.get("client_id") ||
    !url.searchParams.get("state")
  ) {
    throw new Error("Unexpected QuickBooks authorization destination.");
  }
  return url.toString();
}

export async function launchQuickBooksSandbox(
  navigate: (url: string) => void = (url) => window.location.assign(url),
): Promise<void> {
  const response = await apiClient.post<QboSandboxAuthorizationResponse>(
    QBO_SANDBOX_AUTHORIZE_PATH,
  );
  navigate(validatedIntuitAuthorizationUrl(response.data.authorization_url));
}

export async function getQuickBooksSandboxConnection(): Promise<QboSandboxConnectionState> {
  return (
    await apiClient.get<QboSandboxConnectionResponse>(
      QBO_SANDBOX_CONNECTION_PATH,
    )
  ).data.connection_state;
}

export async function disconnectQuickBooksSandbox(): Promise<QboSandboxConnectionState> {
  return (
    await apiClient.post<QboSandboxConnectionResponse>(
      QBO_SANDBOX_DISCONNECT_PATH,
    )
  ).data.connection_state;
}

export async function listRoles(): Promise<CompanyRole[]> {
  return (await apiClient.get<CompanyRole[]>(`${ADMIN_PATH}/roles`)).data;
}

export async function listPermissions(
  roleId?: string,
): Promise<PermissionDefinition[]> {
  return (
    await apiClient.get<PermissionDefinition[]>(`${ADMIN_PATH}/permissions`, {
      params: roleId ? { role_id: roleId } : undefined,
    })
  ).data;
}

export async function grantPermission(
  roleId: string,
  permissionId: string,
): Promise<void> {
  await apiClient.put(
    `${ADMIN_PATH}/roles/${roleId}/permissions/${permissionId}`,
  );
}

export async function removePermission(
  roleId: string,
  permissionId: string,
): Promise<void> {
  await apiClient.delete(
    `${ADMIN_PATH}/roles/${roleId}/permissions/${permissionId}`,
  );
}
