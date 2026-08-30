import { apiClient } from "./client";
import { getMigrationReadiness, getQuickBooksSandboxConnection, type MigrationReadiness, type QboSandboxConnectionState } from "../features/administration/api";

export interface HealthComponent { component: string; state: "HEALTHY" | "DEGRADED" | "NOT_READY" | "BLOCKED" | "UNKNOWN"; required: boolean; classification: string; reason: string; observed_at: string; safe_facts: Record<string, string | number | boolean | null>; }
export interface SystemReadiness { state: HealthComponent["state"]; application: string; version: string; environment: string; observed_at: string; components: HealthComponent[]; }
export interface LaunchRole { code: string; purpose: string; permission_codes: string[]; branch_access_required: boolean; }
export interface PermissionExplanation { permission_code: string; branch_id: string | null; decision: "ALLOWED" | "DENIED"; reasons: string[]; }

export const getSystemReadiness = async () => (await apiClient.get<SystemReadiness>("/health/ready", { validateStatus: (status) => status === 200 || status === 503 })).data;
export const getLaunchRoleMatrix = async () => (await apiClient.get<LaunchRole[]>("/api/v1/authorization/launch-role-matrix")).data;
export const explainPermission = async (permissionCode: string, branchId?: string) => (await apiClient.get<PermissionExplanation>("/api/v1/authorization/explain", { params: { permission_code: permissionCode, branch_id: branchId || undefined } })).data;

export interface IntegrationReadiness { qbo: QboSandboxConnectionState; migration: MigrationReadiness; }
export async function getIntegrationReadiness(): Promise<IntegrationReadiness> {
  const [qbo, migration] = await Promise.all([getQuickBooksSandboxConnection(), getMigrationReadiness()]);
  return { qbo, migration };
}
