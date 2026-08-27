import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AxiosError, AxiosHeaders } from "axios";
import { render, screen, within } from "@testing-library/react";
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
  { id: "permission-read", code: "COMPANY_ENGINEERING_CAPACITY_READ", name: "Capacity Read", description: "View engineering capacity.", scope: "company", active: true, assignable: true, assigned: false, reconciliation_required: false },
  { id: "permission-manage", code: "COMPANY_ENGINEERING_CAPACITY_MANAGE", name: "Capacity Manage", description: "Manage engineering capacity.", scope: "company", active: true, assignable: true, assigned: true, reconciliation_required: false },
  { id: "dispatch-read", code: "COMPANY_DISPATCH_READ", name: "Company Dispatch Read", description: null, scope: "company", active: true, assignable: true, assigned: false, reconciliation_required: false },
  { id: "dispatch-manage", code: "COMPANY_DISPATCH_MANAGE", name: "Company Dispatch Manage", description: null, scope: "company", active: true, assignable: true, assigned: false, reconciliation_required: false },
  { id: "unknown", code: "COMPANY_UNKNOWN_READ", name: "Unknown", description: null, scope: "company", active: true, assignable: false, assigned: false, reconciliation_required: true },
];

const requireReauthentication = vi.fn();
const context: AuthenticationContextValue = {
  status: "authenticated", activeCompany: null, permissionCodes: ["COMPANY_ADMINISTER"],
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
    vi.mocked(api.launchQuickBooksSandbox).mockResolvedValue(undefined);
    vi.mocked(api.getQuickBooksSandboxConnection).mockResolvedValue("not_connected");
    vi.mocked(api.disconnectQuickBooksSandbox).mockResolvedValue("not_connected");
  });

  it("renders assigned and unassigned permissions in a phone-safe single column", async () => {
    renderPage();
    expect(await screen.findByText("COMPANY_ENGINEERING_CAPACITY_READ")).toBeInTheDocument();
    expect(screen.getByText("COMPANY_ENGINEERING_CAPACITY_MANAGE")).toBeInTheDocument();
    expect(screen.getAllByText("Not assigned")).toHaveLength(3);
    expect(screen.getByText("Reconciliation required")).toBeInTheDocument();
    expect(screen.getByText("Assigned")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Grant" })[0]).toHaveClass("min-h-11");
    expect(screen.getByRole("button", { name: "Connect QuickBooks Sandbox" })).toBeInTheDocument();
  });

  it("launches the sandbox through the authenticated API client only after owner click", async () => {
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Connect QuickBooks Sandbox" }));
    expect(api.launchQuickBooksSandbox).toHaveBeenCalledOnce();
  });

  it("requires explicit confirmation before disconnect and restores connect action", async () => {
    vi.mocked(api.getQuickBooksSandboxConnection).mockResolvedValue("connected");
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Disconnect QuickBooks Sandbox" }));
    expect(screen.getByRole("dialog", { name: "Disconnect QuickBooks Sandbox?" })).toBeInTheDocument();
    expect(api.disconnectQuickBooksSandbox).not.toHaveBeenCalled();
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Disconnect QuickBooks Sandbox" }));
    expect(api.disconnectQuickBooksSandbox).toHaveBeenCalledOnce();
    expect(await screen.findByRole("button", { name: "Connect QuickBooks Sandbox" })).toBeInTheDocument();
  });

  it("reports a failed disconnect while retaining the disconnect action", async () => {
    vi.mocked(api.getQuickBooksSandboxConnection).mockResolvedValue("connected");
    vi.mocked(api.disconnectQuickBooksSandbox).mockRejectedValue(new Error("provider rejected"));
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Disconnect QuickBooks Sandbox" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Disconnect QuickBooks Sandbox" }));
    expect(await screen.findByText("Disconnect failed. The existing connection was retained.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Disconnect QuickBooks Sandbox" })).toBeInTheDocument();
  });

  it("finds canonical Dispatch permissions by owner search", async () => {
    renderPage();
    await userEvent.type(await screen.findByPlaceholderText("Search permissions"), "dispatch");
    expect(screen.getByText("COMPANY_DISPATCH_READ")).toBeInTheDocument();
    expect(screen.getByText("COMPANY_DISPATCH_MANAGE")).toBeInTheDocument();
    expect(screen.queryByText("COMPANY_ENGINEERING_CAPACITY_READ")).not.toBeInTheDocument();
  });

  it("fails closed with an explicit authorization message", async () => {
    vi.mocked(api.listRoles).mockRejectedValue(new AxiosError("forbidden", "ERR_BAD_REQUEST", undefined, undefined, { data: null, status: 403, statusText: "Forbidden", headers: {}, config: { headers: new AxiosHeaders() } }));
    renderPage();
    expect(await screen.findByText("You are not authorized to administer Company roles.")).toBeInTheDocument();
  });

  it("confirms a grant then requires fresh authorization and preserves destination", async () => {
    const router = renderPage();
    await userEvent.click((await screen.findAllByRole("button", { name: "Grant" }))[0]);
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
