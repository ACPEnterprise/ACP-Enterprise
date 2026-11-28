import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createMemoryRouter, RouterProvider, useLocation } from "react-router";

import { AuthenticationContext, type AuthenticationContextValue } from "../../src/auth/AuthenticationContext";
import { ApplicationShell } from "../../src/layout/ApplicationShell";
import { availableNavigation } from "../../src/layout/navigation";
import { ThemeProvider } from "../../src/theme/ThemeProvider";
import "../../src/index.css";

const permissions = availableNavigation.flatMap((item) =>
  "requiredPermission" in item && item.requiredPermission ? [item.requiredPermission] : [],
);

const authentication: AuthenticationContextValue = {
  status: "authenticated",
  activeCompany: {
    id: "mobile-qualification-company",
    code: "QUAL",
    name: "Synthetic Mobile Qualification",
    membership_id: "mobile-qualification-membership",
    default_branch_id: null,
    has_all_branch_access: true,
    branches: [],
  },
  user: {
    id: "mobile-qualification-user",
    normalized_email: "mobile.qualification@example.invalid",
    first_name: "Mobile",
    last_name: "Qualification",
    display_name: "Mobile Qualification",
    email_verified_at: null,
  },
  permissionCodes: permissions,
  signIn: async () => undefined,
  signOut: async () => undefined,
  signOutAll: async () => undefined,
  refreshAuthorization: async () => undefined,
  requireReauthentication: () => undefined,
};

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { enabled: false, retry: false },
  },
});

export function RouteProbe() {
  const location = useLocation();
  const label = location.pathname.startsWith("/customers")
    ? "Customer workspace"
    : location.pathname.startsWith("/jobs")
      ? "Job workspace"
      : "Accounting workspace";
  return (
    <section className="p-ui-4 sm:p-ui-6" data-current-route={location.pathname}>
      <h2 className="text-heading-l">{label}</h2>
      <p className="mt-ui-2 text-content-muted">Synthetic shell-only responsive qualification.</p>
    </section>
  );
}

const requestedRoute = new URLSearchParams(window.location.search).get("route") ?? "/customers";
const router = createMemoryRouter([
  {
    path: "/",
    Component: ApplicationShell,
    children: [{ path: "*", Component: RouteProbe }],
  },
], { initialEntries: [requestedRoute] });

const root = document.getElementById("root");
if (!root) throw new Error("Qualification root was not found.");

createRoot(root).render(
  <StrictMode>
    <ThemeProvider preference="light">
      <QueryClientProvider client={queryClient}>
        <AuthenticationContext.Provider value={authentication}>
          <RouterProvider router={router} />
        </AuthenticationContext.Provider>
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
);
