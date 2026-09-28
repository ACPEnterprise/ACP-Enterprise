import { Navigate } from "react-router";

import { useEffectivePermissions } from "../auth/usePermissions";
import {
  COMMAND_CENTER_PERMISSION,
  isFieldTechnicianProfile,
} from "../auth/authorizationProfiles";

export function AuthenticatedLandingRoute() {
  const permissions = useEffectivePermissions();

  if (isFieldTechnicianProfile(permissions)) {
    return <Navigate to="/technician" replace />;
  }
  return (
    <Navigate
      to={permissions.has(COMMAND_CENTER_PERMISSION) ? "/command-center" : "/mission-control"}
      replace
    />
  );
}
