import { Navigate, Outlet, useLocation } from "react-router";

import { useHasPermission } from "../../auth/usePermissions";
import { TECHNICIAN_PERMISSION } from "../../types/technician";

export function TechnicianRouteGuard() {
  const permitted = useHasPermission(TECHNICIAN_PERMISSION);
  const location = useLocation();

  if (!permitted) {
    return (
      <Navigate
        to="/"
        replace
        state={{ deniedPath: location.pathname }}
      />
    );
  }
  return <Outlet />;
}
