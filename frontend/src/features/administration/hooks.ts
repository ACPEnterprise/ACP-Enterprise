import { useMutation, useQuery } from "@tanstack/react-query";

import { shouldRetryApiQuery } from "../../api/errors";
import * as api from "./api";

export const administrationKeys = {
  access: ["administration", "access"] as const,
  roles: ["administration", "roles"] as const,
  permissions: (roleId: string) => ["administration", "permissions", roleId] as const,
};

export function useAdministrationAccess() {
  return useQuery({
    queryKey: administrationKeys.access,
    queryFn: () => api.listPermissions(),
    retry: false,
    staleTime: 60_000,
  });
}

export function useRoles() {
  return useQuery({ queryKey: administrationKeys.roles, queryFn: api.listRoles, retry: shouldRetryApiQuery });
}

export function useRolePermissions(roleId: string | null) {
  return useQuery({
    queryKey: administrationKeys.permissions(roleId ?? "none"),
    queryFn: () => api.listPermissions(roleId ?? undefined),
    enabled: Boolean(roleId),
    retry: shouldRetryApiQuery,
  });
}

export function usePermissionMutation(action: "grant" | "remove") {
  return useMutation({
    mutationFn: ({ roleId, permissionId }: { roleId: string; permissionId: string }) =>
      action === "grant" ? api.grantPermission(roleId, permissionId) : api.removePermission(roleId, permissionId),
    retry: false,
  });
}
