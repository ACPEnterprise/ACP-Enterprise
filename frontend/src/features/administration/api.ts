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

export interface CanonicalRoleSyncPlan {
  company_id: string;
  plan_digest: string;
  safe_to_apply: boolean;
  items: Array<{
    code: string;
    classification: string;
    missing_permissions: string[];
    metadata_update_required: boolean;
  }>;
}

export interface CanonicalRoleSyncResult {
  plan: CanonicalRoleSyncPlan;
  roles_created: string[];
  permissions_added: string[];
  metadata_restored: string[];
  authorization_users_advanced: number;
}

export interface IdentityOnboardingView {
  id: string;
  employee_id: string;
  membership_id: string;
  branch_id: string;
  masked_login: string;
  status: string;
}

export interface IdentityOnboardingInitiateRequest {
  request_key: "acp-employee-beta-v1";
  branch_id: string;
  first_name: "ACP Employee";
  last_name: "Beta";
  display_name: "ACP Employee Beta";
  employee_type: "employee";
  employee_number_prefix: "EMP-";
  employee_number_width: 4;
  role_ids: [string];
  login_email: string;
}

export interface IdentityOnboardingDeliveryView {
  request_id: string;
  invitation_id: string;
  message_id: string | null;
  invitation_status: string;
  delivery_status: string;
  template_version: string | null;
  retry_count: number;
  provider_reference_present: boolean;
  last_error_code: string | null;
  created_at: string | null;
  submitted_at: string | null;
  delivered_at: string | null;
}

const ADMIN_PATH = "/api/v1/company-admin";
const QBO_SANDBOX_AUTHORIZE_PATH = "/api/v1/integrations/qbo/oauth/authorize";
const QBO_SANDBOX_CONNECTION_PATH = "/api/v1/integrations/qbo/connection";
const QBO_SANDBOX_DISCONNECT_PATH = "/api/v1/integrations/qbo/oauth/disconnect";
const QBO_PRODUCTION_AUTHORIZE_PATH =
  "/api/v1/integrations/qbo/production/oauth/authorize";
const MIGRATION_READINESS_PATH = "/api/v1/migration/readiness";

export interface MigrationReadiness {
  overall_status: string;
  current_phase: string;
  authority_digest: string;
  reconciliation_digest: string;
  stale: boolean;
  safe_failure_code: string | null;
  go_no_go: {
    state: string;
    activation_eligible: boolean;
    blockers: string[];
  };
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
  decision_packets: Array<{
    decision_id: string;
    question: string;
    current_evidence: string;
    options: string[];
    recommended_default: string | null;
    risk: string;
    unlocks: string;
    state: string;
  }>;
  freeze_authority: {
    state: string;
    required_authority: string;
    sources: string[];
    evidence: string;
    late_change_behavior: string;
    reopen_behavior: string;
  };
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
  status: "sandbox_oauth_initiation" | "qbo_production_oauth_initiation";
  authorization_url: string;
}

function validatedIntuitAuthorizationUrl(
  value: string,
  callbackPath = "/api/v1/integrations/qbo/oauth/callback",
): string {
  const url = new URL(value);
  const expectedCallback = `${window.location.origin}${callbackPath}`;
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

export async function launchQuickBooksProduction(
  navigate: (url: string) => void = (url) => window.location.assign(url),
): Promise<void> {
  const response = await apiClient.post<QboSandboxAuthorizationResponse>(
    QBO_PRODUCTION_AUTHORIZE_PATH,
  );
  navigate(
    validatedIntuitAuthorizationUrl(
      response.data.authorization_url,
      "/api/v1/integrations/qbo/production/oauth/callback",
    ),
  );
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

export async function getCanonicalRoleSyncPlan(): Promise<CanonicalRoleSyncPlan> {
  return (
    await apiClient.get<CanonicalRoleSyncPlan>(
      `${ADMIN_PATH}/canonical-roles/reconciliation`,
    )
  ).data;
}

export async function applyCanonicalRoleSync(
  expectedPlanDigest: string,
): Promise<CanonicalRoleSyncResult> {
  return (
    await apiClient.post<CanonicalRoleSyncResult>(
      `${ADMIN_PATH}/canonical-roles/reconciliation/apply`,
      { expected_plan_digest: expectedPlanDigest },
    )
  ).data;
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

export async function initiateEmployeeBetaOnboarding(
  request: IdentityOnboardingInitiateRequest,
): Promise<IdentityOnboardingView> {
  return (
    await apiClient.post<IdentityOnboardingView>(
      "/api/v1/identity-onboarding",
      request,
    )
  ).data;
}

export async function getIdentityOnboardingDelivery(
  requestId: string,
): Promise<IdentityOnboardingDeliveryView> {
  return (
    await apiClient.get<IdentityOnboardingDeliveryView>(
      `/api/v1/identity-onboarding/${requestId}/delivery`,
    )
  ).data;
}

export async function reissueIdentityOnboarding(
  requestId: string,
): Promise<IdentityOnboardingView> {
  return (
    await apiClient.post<IdentityOnboardingView>(
      `/api/v1/identity-onboarding/${requestId}/reissue`,
    )
  ).data;
}

export async function revokeIdentityOnboarding(
  requestId: string,
): Promise<IdentityOnboardingView> {
  return (
    await apiClient.post<IdentityOnboardingView>(
      `/api/v1/identity-onboarding/${requestId}/revoke`,
    )
  ).data;
}
