import { Navigate } from "react-router";

import { useAuth } from "../auth";
import { useEffectivePermissions } from "../auth/usePermissions";
import {
  COMMAND_CENTER_PERMISSION,
  isFieldTechnicianProfile,
} from "../auth/authorizationProfiles";
import { isCommercialOnboardingComplete } from "../onboarding/commercialOnboardingState";

export function AuthenticatedLandingRoute() {
  const { activeCompany } = useAuth();
  const permissions = useEffectivePermissions();

  if (isFieldTechnicianProfile(permissions)) {
    return <Navigate to="/technician" replace />;
  }
  if (activeCompany && !isCommercialOnboardingComplete(activeCompany.id)) {
    return <Navigate to="/onboarding" replace />;
  }
  return (
    <Navigate
      to={permissions.has(COMMAND_CENTER_PERMISSION) ? "/command-center" : "/mission-control"}
      replace
    />
  );
}
