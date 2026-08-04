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
}

const ADMIN_PATH = "/api/v1/company-admin";

export async function listRoles(): Promise<CompanyRole[]> {
  return (await apiClient.get<CompanyRole[]>(`${ADMIN_PATH}/roles`)).data;
}

export async function listPermissions(roleId?: string): Promise<PermissionDefinition[]> {
  return (await apiClient.get<PermissionDefinition[]>(`${ADMIN_PATH}/permissions`, {
    params: roleId ? { role_id: roleId } : undefined,
  })).data;
}

export async function grantPermission(roleId: string, permissionId: string): Promise<void> {
  await apiClient.put(`${ADMIN_PATH}/roles/${roleId}/permissions/${permissionId}`);
}

export async function removePermission(roleId: string, permissionId: string): Promise<void> {
  await apiClient.delete(`${ADMIN_PATH}/roles/${roleId}/permissions/${permissionId}`);
}
