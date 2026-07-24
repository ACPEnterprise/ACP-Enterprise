import { Navigate, Outlet, useLocation } from "react-router";

import { Spinner } from "../ui";
import { useAuth } from "./useAuth";

export function ProtectedRoute() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "restoring") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-app-background text-content">
        <div className="text-center">
          <p className="mb-ui-4 text-overline uppercase tracking-[0.16em] text-content-muted">ACP Enterprise</p>
          <Spinner label="Initializing Command Center" size="large" />
        </div>
      </div>
    );
  }
  if (status === "unauthenticated") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}
