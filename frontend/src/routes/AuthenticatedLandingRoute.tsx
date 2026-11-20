import { Navigate } from "react-router";

import { useEffectivePermissions } from "../auth/usePermissions";
import {
  COMMAND_CENTER_PERMISSION,
  CUSTOMER_OPERATIONS_PERMISSION,
  isFieldTechnicianProfile,
} from "../auth/authorizationProfiles";

export function AuthenticatedLandingRoute() {
  const permissions = useEffectivePermissions();

  if (isFieldTechnicianProfile(permissions)) {
    return <Navigate to="/technician" replace />;
  }
  if (permissions.has(COMMAND_CENTER_PERMISSION)) {
    return <Navigate to="/command-center" replace />;
  }
  if (permissions.has(CUSTOMER_OPERATIONS_PERMISSION)) {
    return <Navigate to="/customers" replace />;
  }
  return (
    <Navigate to="/mission-control" replace />
  );
}
