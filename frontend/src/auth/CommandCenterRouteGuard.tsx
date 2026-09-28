import { Navigate, Outlet } from "react-router";

import { useEffectivePermissions } from "./usePermissions";
import {
  COMMAND_CENTER_PERMISSION,
  isFieldTechnicianProfile,
} from "./authorizationProfiles";

export function CommandCenterRouteGuard() {
  const permissions = useEffectivePermissions();

  if (permissions.has(COMMAND_CENTER_PERMISSION)) return <Outlet />;

  return (
    <Navigate
      to={isFieldTechnicianProfile(permissions) ? "/technician" : "/mission-control"}
      replace
      state={{ deniedPath: "/command-center" }}
    />
  );
}
