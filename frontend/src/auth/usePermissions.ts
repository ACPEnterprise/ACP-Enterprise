import { useMemo } from "react";

import { useAuth } from "./useAuth";

export function useEffectivePermissions(): ReadonlySet<string> {
  const { permissionCodes = [] } = useAuth();
  return useMemo(() => new Set(permissionCodes), [permissionCodes]);
}

export function useHasPermission(permissionCode: string): boolean {
  return useEffectivePermissions().has(permissionCode);
}
