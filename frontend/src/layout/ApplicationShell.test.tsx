import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthenticationContext, type AuthenticationContextValue } from "../auth/AuthenticationContext";
import { ThemeProvider } from "../theme/ThemeProvider";
import { availableNavigation } from "./navigation";
import { ApplicationShell } from "./ApplicationShell";

vi.mock("../hooks/useAccessAgreement", () => ({
  useCurrentAccessAgreement: () => ({ data: { required: false, accepted: true } }),
}));

vi.mock("../features/administration/hooks", () => ({
  useAdministrationAccess: () => ({ isSuccess: true }),
}));

vi.mock("./AIWorkspace", () => ({ AIWorkspace: () => null }));
vi.mock("./NotificationCenterRegion", () => ({ NotificationCenterRegion: () => null }));

const allPermissions = availableNavigation.flatMap((item) =>
  "requiredPermission" in item && item.requiredPermission ? [item.requiredPermission] : [],
);

function authentication(permissionCodes: readonly string[] = allPermissions): AuthenticationContextValue {
  return {
    status: "authenticated",
    activeCompany: {
      id: "company-1",
      code: "ACP",
      name: "All County Plumbing",
      membership_id: "membership-1",
      default_branch_id: null,
      has_all_branch_access: true,
      branches: [],
    },
    user: {
      id: "user-1",
      normalized_email: "admin@example.com",
      first_name: "Preview",
      last_name: "Administrator",
      display_name: "Preview Administrator",
      email_verified_at: null,
    },
    permissionCodes,
    signIn: async () => undefined,
    signOut: async () => undefined,
    signOutAll: async () => undefined,
    refreshAuthorization: async () => undefined,
    requireReauthentication: () => undefined,
  };
}

function renderShell(permissionCodes: readonly string[] = allPermissions) {
  const router = createMemoryRouter([
    {
      path: "/",
      Component: ApplicationShell,
      children: [
        { index: true, element: <p>Company setup</p> },
        { path: "*", element: <p>Destination workspace</p> },
      ],
    },
  ]);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const result = render(
    <ThemeProvider preference="light">
      <QueryClientProvider client={queryClient}>
        <AuthenticationContext.Provider value={authentication(permissionCodes)}>
          <RouterProvider router={router} />
        </AuthenticationContext.Provider>
      </QueryClientProvider>
    </ThemeProvider>,
  );
  return { ...result, router };
}

describe("ApplicationShell mobile navigation", () => {
  beforeEach(() => {
    vi.spyOn(window, "scrollTo").mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("keeps the persistent sidebar out of mobile layout and opens an accessible overlay", async () => {
    const user = userEvent.setup();
    const { container } = renderShell();
    const trigger = screen.getByRole("button", { name: "Open navigation" });
    const desktopNavigation = screen.getByRole("complementary", { name: "Application navigation", hidden: true });

    expect(desktopNavigation).toHaveClass("hidden", "lg:flex");
    expect(trigger).toHaveClass("lg:hidden");
    expect(trigger).toHaveAttribute("aria-controls", "mobile-application-navigation");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(container.querySelector(".theme-shell")).not.toHaveAttribute("data-mobile-navigation-open");

    await user.click(trigger);

    const drawer = screen.getByRole("dialog", { name: "Mobile application navigation" });
    expect(drawer).toHaveAttribute("id", "mobile-application-navigation");
    expect(drawer).toHaveAttribute("aria-modal", "true");
    expect(drawer).toHaveClass("theme-navigation-mobile", "safe-area-drawer", "lg:hidden");
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(container.querySelector(".theme-shell")).toHaveAttribute("inert");
    expect(document.body.style.position).toBe("fixed");
    expect(document.body.style.overflow).toBe("hidden");
    expect(document.documentElement.style.overflow).toBe("hidden");
    expect(within(drawer).getByRole("link", { name: "Customers" })).toBeInTheDocument();
    expect(within(drawer).getByRole("link", { name: "Dispatch" })).toBeInTheDocument();
    expect(within(drawer).getByRole("link", { name: "Accounting" })).toBeInTheDocument();
    expect(within(drawer).getByRole("link", { name: "Employees" })).toBeInTheDocument();
    expect(within(drawer).getByRole("link", { name: "Payroll" })).toBeInTheDocument();
    expect(within(drawer).getByRole("button", { name: "Close navigation" })).toHaveFocus();
  });

  it("closes from a destination, the backdrop, the close control, and Escape", async () => {
    const user = userEvent.setup();
    const { router } = renderShell();
    const trigger = screen.getByRole("button", { name: "Open navigation" });

    await user.click(trigger);
    await user.click(within(screen.getByRole("dialog")).getByRole("link", { name: "Customers" }));
    expect(router.state.location.pathname).toBe("/customers");
    expect(screen.queryByRole("dialog", { name: "Mobile application navigation" })).not.toBeInTheDocument();

    await user.click(trigger);
    await user.click(document.querySelector<HTMLButtonElement>(".theme-navigation-backdrop")!);
    expect(screen.queryByRole("dialog", { name: "Mobile application navigation" })).not.toBeInTheDocument();

    await user.click(trigger);
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Close navigation" }));
    expect(screen.queryByRole("dialog", { name: "Mobile application navigation" })).not.toBeInTheDocument();
    await waitFor(() => expect(trigger).toHaveFocus());

    await user.click(trigger);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Mobile application navigation" })).not.toBeInTheDocument();
    await waitFor(() => expect(trigger).toHaveFocus());
    expect(document.body.style.position).toBe("");
    expect(document.body.style.overflow).toBe("");
  });

  it("renders only navigation authorized for the authenticated user", async () => {
    const user = userEvent.setup();
    renderShell(["COMPANY_CUSTOMER_READ"]);

    await user.click(screen.getByRole("button", { name: "Open navigation" }));
    const drawer = screen.getByRole("dialog", { name: "Mobile application navigation" });
    expect(within(drawer).getByRole("link", { name: "Customers" })).toBeInTheDocument();
    expect(within(drawer).queryByRole("link", { name: "Dispatch" })).not.toBeInTheDocument();
    expect(within(drawer).queryByRole("link", { name: "Accounting" })).not.toBeInTheDocument();
    expect(within(drawer).queryByRole("link", { name: "Employees" })).not.toBeInTheDocument();
    expect(within(drawer).queryByRole("link", { name: "Payroll" })).not.toBeInTheDocument();
  });
});
