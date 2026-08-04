import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { AuthenticationContext, type AuthenticationContextValue } from "../auth/AuthenticationContext";
import { brandConfig } from "../branding/brandConfig";
import { ThemeProvider } from "../theme/ThemeProvider";
import { ApplicationHeader } from "./ApplicationHeader";

const authentication: AuthenticationContextValue = {
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
  signIn: async () => undefined,
  signOut: async () => undefined,
  signOutAll: async () => undefined,
  requireReauthentication: () => undefined,
};

function AuthenticatedHeader({ metadata }: { metadata: { pageTitle: string; breadcrumbs: Array<{ label: string; path?: string }> } }) {
  return (
    <MemoryRouter>
      <ThemeProvider preference="dark">
        <AuthenticationContext.Provider value={authentication}>
          <ApplicationHeader brand={brandConfig} metadata={metadata} onOpenNavigation={() => undefined} navigationTriggerRef={createRef()} />
        </AuthenticationContext.Provider>
      </ThemeProvider>
    </MemoryRouter>
  );
}

describe("ApplicationHeader", () => {
  it("renders route metadata and accessible breadcrumbs", () => {
    render(<AuthenticatedHeader metadata={{ pageTitle: "Customer Detail", breadcrumbs: [{ label: "Customers", path: "/customers" }, { label: "Customer Detail" }] }} />);
    expect(screen.getByRole("heading", { name: "Customer Detail" })).toBeInTheDocument();
    const breadcrumbs = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(breadcrumbs).toBeInTheDocument();
    expect(within(breadcrumbs).getByText("Customer Detail")).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("Welcome, Preview")).toBeInTheDocument();
    expect(screen.getByText("All County Plumbing")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Command Center Online");
  });

  it("changes the active theme preference", async () => {
    const user = userEvent.setup();
    render(<AuthenticatedHeader metadata={{ pageTitle: "Mission Control", breadcrumbs: [] }} />);
    await user.selectOptions(screen.getByRole("combobox", { name: "Theme preference" }), "light");
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
  });

  it("applies the shared safe-area header boundary", () => {
    const { container } = render(
      <AuthenticatedHeader metadata={{ pageTitle: "Command Center", breadcrumbs: [] }} />,
    );
    expect(container.querySelector("header")).toHaveClass("safe-area-header");
  });
});
