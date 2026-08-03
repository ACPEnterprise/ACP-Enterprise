import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AxiosError, AxiosHeaders } from "axios";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthenticationContext, type AuthenticationContextValue } from "../../auth/AuthenticationContext";
import { ThemeProvider } from "../../theme/ThemeProvider";
import * as api from "./api";
import { AdministrationRoute } from "./AdministrationRoute";

vi.mock("./api");

const role = { id: "role-1", company_id: "company-1", code: "COMPANY_ADMINISTRATOR", name: "Company Administrator", description: null, status: "active", is_system: true };
const permissions = [
  { id: "permission-read", code: "COMPANY_ENGINEERING_CAPACITY_READ", name: "Capacity Read", description: "View engineering capacity.", scope: "company", active: true, assignable: true, assigned: false },
  { id: "permission-manage", code: "COMPANY_ENGINEERING_CAPACITY_MANAGE", name: "Capacity Manage", description: "Manage engineering capacity.", scope: "company", active: true, assignable: true, assigned: true },
];

const requireReauthentication = vi.fn();
const context: AuthenticationContextValue = {
  status: "authenticated", activeCompany: null,
  user: { id: "owner", normalized_email: "owner@example.com", first_name: "Owner", last_name: "User", display_name: "Owner", email_verified_at: null },
  signIn: vi.fn(), signOut: vi.fn(), signOutAll: vi.fn(), requireReauthentication,
};

function renderPage() {
  const router = createMemoryRouter([
    { path: "/administration", Component: AdministrationRoute },
    { path: "/login", element: <p>Reauthentication required</p> },
  ], { initialEntries: ["/administration"] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<ThemeProvider preference="dark"><AuthenticationContext.Provider value={context}><QueryClientProvider client={client}><RouterProvider router={router} /></QueryClientProvider></AuthenticationContext.Provider></ThemeProvider>);
  return router;
}

describe("AdministrationRoute", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.listRoles).mockResolvedValue([role]);
    vi.mocked(api.listPermissions).mockResolvedValue(permissions);
    vi.mocked(api.grantPermission).mockResolvedValue(undefined);
    vi.mocked(api.removePermission).mockResolvedValue(undefined);
  });

  it("renders assigned and unassigned permissions in a phone-safe single column", async () => {
    renderPage();
    expect(await screen.findByText("COMPANY_ENGINEERING_CAPACITY_READ")).toBeInTheDocument();
    expect(screen.getByText("COMPANY_ENGINEERING_CAPACITY_MANAGE")).toBeInTheDocument();
    expect(screen.getByText("Not assigned")).toBeInTheDocument();
    expect(screen.getByText("Assigned")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Grant" })).toHaveClass("min-h-11");
  });

  it("fails closed with an explicit authorization message", async () => {
    vi.mocked(api.listRoles).mockRejectedValue(new AxiosError("forbidden", "ERR_BAD_REQUEST", undefined, undefined, { data: null, status: 403, statusText: "Forbidden", headers: {}, config: { headers: new AxiosHeaders() } }));
    renderPage();
    expect(await screen.findByText("You are not authorized to administer Company roles.")).toBeInTheDocument();
  });

  it("confirms a grant then requires fresh authorization and preserves destination", async () => {
    const router = renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Grant" }));
    expect(screen.getByRole("dialog", { name: "Grant permission?" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Grant permission" }));
    expect(await screen.findByText("Reauthentication required")).toBeInTheDocument();
    expect(api.grantPermission).toHaveBeenCalledWith("role-1", "permission-read");
    expect(requireReauthentication).toHaveBeenCalledOnce();
    expect(router.state.location.state).toEqual({ from: "/administration", authorizationChanged: true });
  });

  it("confirms removal and clearly reports a rejected mutation", async () => {
    vi.mocked(api.removePermission).mockRejectedValue(new Error("rejected"));
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Remove" }));
    await userEvent.click(screen.getByRole("button", { name: "Remove permission" }));
    expect(await screen.findByText("The permission change was not accepted. Your role was not changed.")).toBeInTheDocument();
    expect(requireReauthentication).not.toHaveBeenCalled();
  });
});
