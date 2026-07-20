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
  activeCompany: null,
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
  });

  it("changes the active theme preference", async () => {
    const user = userEvent.setup();
    render(<AuthenticatedHeader metadata={{ pageTitle: "Mission Control", breadcrumbs: [] }} />);
    await user.selectOptions(screen.getByRole("combobox", { name: "Theme preference" }), "light");
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
  });
});
