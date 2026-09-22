import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AxiosError, AxiosHeaders } from "axios";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  AuthenticationContext,
  type AuthenticationContextValue,
} from "../../auth/AuthenticationContext";
import { ThemeProvider } from "../../theme/ThemeProvider";
import * as api from "./api";
import { AdministrationRoute } from "./AdministrationRoute";

vi.mock("./api");

const role = {
  id: "role-1",
  company_id: "company-1",
  code: "COMPANY_ADMINISTRATOR",
  name: "Company Administrator",
  description: null,
  status: "active",
  is_system: true,
};
const permissions = [
  {
    id: "permission-read",
    code: "COMPANY_ENGINEERING_CAPACITY_READ",
    name: "Capacity Read",
    description: "View engineering capacity.",
    scope: "company",
    active: true,
    assignable: true,
    assigned: false,
    reconciliation_required: false,
  },
  {
    id: "permission-manage",
    code: "COMPANY_ENGINEERING_CAPACITY_MANAGE",
    name: "Capacity Manage",
    description: "Manage engineering capacity.",
    scope: "company",
    active: true,
    assignable: true,
    assigned: true,
    reconciliation_required: false,
  },
  {
    id: "dispatch-read",
    code: "COMPANY_DISPATCH_READ",
    name: "Company Dispatch Read",
    description: null,
    scope: "company",
    active: true,
    assignable: true,
    assigned: false,
    reconciliation_required: false,
  },
  {
    id: "dispatch-manage",
    code: "COMPANY_DISPATCH_MANAGE",
    name: "Company Dispatch Manage",
    description: null,
    scope: "company",
    active: true,
    assignable: true,
    assigned: false,
    reconciliation_required: false,
  },
  {
    id: "unknown",
    code: "COMPANY_UNKNOWN_READ",
    name: "Unknown",
    description: null,
    scope: "company",
    active: true,
    assignable: false,
    assigned: false,
    reconciliation_required: true,
  },
];

const requireReauthentication = vi.fn();
const refreshAuthorization = vi.fn().mockResolvedValue(undefined);
const context: AuthenticationContextValue = {
  status: "authenticated",
  activeCompany: null,
  permissionCodes: ["COMPANY_ADMINISTER", "COMPANY_ROLE_READ", "COMPANY_ROLE_MANAGE", "COMPANY_PERMISSION_MANAGE", "COMPANY_MEMBERSHIP_READ"],
  user: {
    id: "owner",
    normalized_email: "owner@example.com",
    first_name: "Owner",
    last_name: "User",
    display_name: "Owner",
    email_verified_at: null,
  },
  signIn: vi.fn(),
  signOut: vi.fn(),
  signOutAll: vi.fn(),
  refreshAuthorization,
  requireReauthentication,
};

function renderPage() {
  const router = createMemoryRouter(
    [
      { path: "/administration", Component: AdministrationRoute },
      { path: "/login", element: <p>Reauthentication required</p> },
    ],
    { initialEntries: ["/administration"] },
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <ThemeProvider preference="dark">
      <AuthenticationContext.Provider value={context}>
        <QueryClientProvider client={client}>
          <RouterProvider router={router} />
        </QueryClientProvider>
      </AuthenticationContext.Provider>
    </ThemeProvider>,
  );
  return router;
}

describe("AdministrationRoute", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    context.permissionCodes = ["COMPANY_ADMINISTER", "COMPANY_ROLE_READ", "COMPANY_ROLE_MANAGE", "COMPANY_PERMISSION_MANAGE", "COMPANY_MEMBERSHIP_READ"];
    vi.mocked(api.listRoles).mockResolvedValue([role]);
    vi.mocked(api.listMemberships).mockResolvedValue([
      { id: "membership-active", user_id: "owner", company_id: "company-1", status: "active", default_branch_id: "branch-1", has_all_branch_access: false, display_name: "Lianne Hernandez", email: "lianne@example.com", branch_name: "Main Branch", role_ids: [], role_codes: [] },
      { id: "membership-same-name", user_id: "other-user", company_id: "company-1", status: "active", default_branch_id: "branch-2", has_all_branch_access: false, display_name: "Lianne Hernandez", email: "other@example.com", branch_name: "North Branch", role_ids: [], role_codes: [] },
      { id: "membership-inactive", user_id: "former-user", company_id: "company-1", status: "suspended", default_branch_id: "branch-2", has_all_branch_access: true, display_name: "Former User", email: "former@example.com", branch_name: "North Branch", role_ids: [], role_codes: [] },
    ]);
    vi.mocked(api.createRole).mockResolvedValue({
      id: "role-source4", company_id: "company-1", code: "SOURCE4_PREVIEW_ADMISSION", name: "SOURCE.4 Preview Admission", description: null, status: "active", is_system: false,
    });
    vi.mocked(api.assignMembershipRole).mockResolvedValue(undefined);
    vi.mocked(api.revokeMembershipRole).mockResolvedValue(undefined);
    vi.mocked(api.listPermissions).mockResolvedValue(permissions);
    vi.mocked(api.grantPermission).mockResolvedValue(undefined);
    vi.mocked(api.removePermission).mockResolvedValue(undefined);
    vi.mocked(api.getCanonicalRoleSyncPlan).mockResolvedValue({
      company_id: "company-1",
      plan_digest: "a".repeat(64),
      safe_to_apply: true,
      items: [
        {
          code: "SERVICE_CSR",
          classification: "MISSING_CANONICAL_ROLE",
          missing_permissions: ["COMPANY_CUSTOMER_READ"],
          metadata_update_required: false,
        },
        {
          code: "OWN_DATA_ROLE",
          classification: "ALREADY_CONFORMING",
          missing_permissions: [],
          metadata_update_required: false,
        },
      ],
    });
    vi.mocked(api.applyCanonicalRoleSync).mockResolvedValue({
      plan: {
        company_id: "company-1",
        plan_digest: "a".repeat(64),
        safe_to_apply: true,
        items: [],
      },
      roles_created: ["SERVICE_CSR"],
      permissions_added: [],
      metadata_restored: [],
      authorization_users_advanced: 0,
    });
    vi.mocked(api.launchQuickBooksSandbox).mockResolvedValue(undefined);
    vi.mocked(api.launchQuickBooksProduction).mockResolvedValue(undefined);
    vi.mocked(api.getQuickBooksSandboxConnection).mockResolvedValue(
      "not_connected",
    );
    vi.mocked(api.disconnectQuickBooksSandbox).mockResolvedValue(
      "not_connected",
    );
    vi.mocked(api.getMigrationReadiness).mockResolvedValue({
      overall_status: "external_owner_gate",
      current_phase: "owner_ready",
      authority_digest: "a".repeat(64),
      reconciliation_digest: "b".repeat(64),
      stale: false,
      safe_failure_code: null,
      go_no_go: {
        state: "external_auth_required",
        activation_eligible: false,
        blockers: [],
      },
      historical_window: {
        starts_on: null,
        ends_on: "2026-08-30",
        opening_evidence_state: "owner_decision_required",
        completeness: "configuration_required",
      },
      sources: [],
      counts: [],
      timeline: [],
      authority_states: [],
      owner_decisions: [],
      decision_packets: [],
      freeze_authority: {
        state: "external_authorization_required",
        required_authority: "owner_go_no_go_actor",
        sources: [],
        evidence: "immutable_source_timestamps_and_manifest_digests",
        late_change_behavior: "invalidate_delta_and_return_to_reconciliation",
        reopen_behavior: "new_freeze_generation_required",
      },
      run_history: [],
      recovery_state: "completed_runs_replay_safe",
    });
  });

  it("previews and applies only a safe canonical role plan", async () => {
    const user = userEvent.setup();
    const router = renderPage();
    expect(await screen.findByText("Canonical role readiness")).toBeInTheDocument();
    expect(screen.getByText("MISSING CANONICAL ROLE")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Apply safe reconciliation" }));
    expect(vi.mocked(api.applyCanonicalRoleSync).mock.calls[0]?.[0]).toBe(
      "a".repeat(64),
    );
    expect(refreshAuthorization).toHaveBeenCalledOnce();
    expect(requireReauthentication).not.toHaveBeenCalled();
    expect(router.state.location.pathname).toBe("/administration");
  });

  it("renders assigned and unassigned permissions in a phone-safe single column", async () => {
    renderPage();
    expect(
      await screen.findByText("COMPANY_ENGINEERING_CAPACITY_READ"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("COMPANY_ENGINEERING_CAPACITY_MANAGE"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Not assigned")).toHaveLength(3);
    expect(screen.getByText("Reconciliation required")).toBeInTheDocument();
    expect(screen.getByText("Assigned")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Grant" })[0]).toHaveClass(
      "min-h-11",
    );
    expect(
      screen.getByRole("button", { name: "Connect QuickBooks Sandbox" }),
    ).toBeInTheDocument();
  });

  it("launches the sandbox through the authenticated API client only after owner click", async () => {
    renderPage();
    await userEvent.click(
      await screen.findByRole("button", { name: "Connect QuickBooks Sandbox" }),
    );
    expect(api.launchQuickBooksSandbox).toHaveBeenCalledOnce();
  });

  it("separates the real read-only QuickBooks action from Development sandbox", async () => {
    renderPage();
    expect(
      await screen.findByText("QuickBooks REAL company — read-only migration source"),
    ).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Connect REAL QuickBooks — Read Only" }),
    );
    expect(api.launchQuickBooksProduction).toHaveBeenCalledOnce();
    expect(api.launchQuickBooksSandbox).not.toHaveBeenCalled();
  });

  it("requires explicit confirmation before disconnect and restores connect action", async () => {
    vi.mocked(api.getQuickBooksSandboxConnection).mockResolvedValue(
      "connected",
    );
    renderPage();
    await userEvent.click(
      await screen.findByRole("button", {
        name: "Disconnect QuickBooks Sandbox",
      }),
    );
    expect(
      screen.getByRole("dialog", { name: "Disconnect QuickBooks Sandbox?" }),
    ).toBeInTheDocument();
    expect(api.disconnectQuickBooksSandbox).not.toHaveBeenCalled();
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", {
        name: "Disconnect QuickBooks Sandbox",
      }),
    );
    expect(api.disconnectQuickBooksSandbox).toHaveBeenCalledOnce();
    expect(
      await screen.findByRole("button", { name: "Connect QuickBooks Sandbox" }),
    ).toBeInTheDocument();
  });

  it("reports a failed disconnect while retaining the disconnect action", async () => {
    vi.mocked(api.getQuickBooksSandboxConnection).mockResolvedValue(
      "connected",
    );
    vi.mocked(api.disconnectQuickBooksSandbox).mockRejectedValue(
      new Error("provider rejected"),
    );
    renderPage();
    await userEvent.click(
      await screen.findByRole("button", {
        name: "Disconnect QuickBooks Sandbox",
      }),
    );
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", {
        name: "Disconnect QuickBooks Sandbox",
      }),
    );
    expect(
      await screen.findByText(
        "Disconnect failed. The existing connection was retained.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Disconnect QuickBooks Sandbox" }),
    ).toBeInTheDocument();
  });

  it("finds canonical Dispatch permissions by owner search", async () => {
    renderPage();
    await userEvent.type(
      await screen.findByPlaceholderText("Search permissions"),
      "dispatch",
    );
    expect(screen.getByText("COMPANY_DISPATCH_READ")).toBeInTheDocument();
    expect(screen.getByText("COMPANY_DISPATCH_MANAGE")).toBeInTheDocument();
    expect(
      screen.queryByText("COMPANY_ENGINEERING_CAPACITY_READ"),
    ).not.toBeInTheDocument();
  });

  it("fails closed with an explicit authorization message", async () => {
    vi.mocked(api.listRoles).mockRejectedValue(
      new AxiosError("forbidden", "ERR_BAD_REQUEST", undefined, undefined, {
        data: null,
        status: 403,
        statusText: "Forbidden",
        headers: {},
        config: { headers: new AxiosHeaders() },
      }),
    );
    renderPage();
    expect(
      await screen.findByText(
        "You are not authorized to administer Company roles.",
      ),
    ).toBeInTheDocument();
  });

  it("confirms a grant once, refreshes authorization, and stays in Administration", async () => {
    const router = renderPage();
    await userEvent.click(
      (await screen.findAllByRole("button", { name: "Grant" }))[0],
    );
    expect(
      screen.getByRole("dialog", { name: "Grant permission?" }),
    ).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Grant permission" }),
    );
    expect(await screen.findByText("Role Administration")).toBeInTheDocument();
    expect(api.grantPermission).toHaveBeenCalledWith(
      "role-1",
      "permission-read",
    );
    expect(refreshAuthorization).toHaveBeenCalledOnce();
    expect(requireReauthentication).not.toHaveBeenCalled();
    expect(router.state.location.pathname).toBe("/administration");
  });

  it("confirms removal and clearly reports a rejected mutation", async () => {
    vi.mocked(api.removePermission).mockRejectedValue(new Error("rejected"));
    renderPage();
    await userEvent.click(
      await screen.findByRole("button", { name: "Remove" }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Remove permission" }),
    );
    expect(
      await screen.findByText(
        "The permission change was not accepted. Your role was not changed.",
      ),
    ).toBeInTheDocument();
    expect(refreshAuthorization).not.toHaveBeenCalled();
  });

  it("keeps role evidence read-only without permission-manage authority", async () => {
    context.permissionCodes = ["COMPANY_ROLE_READ"];
    renderPage();

    expect(await screen.findByText("COMPANY_DISPATCH_READ")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Grant" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove" })).not.toBeInTheDocument();
  });

  it("creates an empty Company role without accepting Company or Branch scope", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.type(await screen.findByPlaceholderText("SOURCE4_PREVIEW_ADMISSION"), "SOURCE4_PREVIEW_ADMISSION");
    await user.type(screen.getByPlaceholderText("SOURCE.4 Preview Admission"), "SOURCE.4 Preview Admission");
    await user.click(screen.getByRole("button", { name: "Create role" }));
    expect(vi.mocked(api.createRole).mock.calls[0]?.[0]).toEqual({
      code: "SOURCE4_PREVIEW_ADMISSION",
      name: "SOURCE.4 Preview Admission",
      description: null,
    });
  });

  it("saves one selected role once for a visible active Membership without login redirect", async () => {
    const router = renderPage();
    const membership = await screen.findByRole("combobox", { name: "Active Membership" });
    expect(
      within(membership).getByRole("option", {
        name: "Lianne Hernandez — Main Branch — Active · lianne@example.com",
      }),
    ).toHaveValue("membership-active");
    expect(
      within(membership).queryByRole("option", {
        name: /Former User/,
      }),
    ).not.toBeInTheDocument();
    expect(
      within(membership).getByRole("option", {
        name: "Lianne Hernandez — North Branch — Active · other@example.com",
      }),
    ).toHaveValue("membership-same-name");
    await userEvent.selectOptions(membership, "membership-active");
    await userEvent.click(screen.getByRole("checkbox", { name: /Company Administrator/ }));
    await userEvent.click(screen.getByRole("button", { name: "Save access" }));
    expect(vi.mocked(api.assignMembershipRole).mock.calls[0]?.slice(0, 2)).toEqual([
      "membership-active",
      "role-1",
    ]);
    expect(api.assignMembershipRole).toHaveBeenCalledTimes(1);
    expect(refreshAuthorization).toHaveBeenCalledOnce();
    expect(requireReauthentication).not.toHaveBeenCalled();
    expect(router.state.location.pathname).toBe("/administration");
  });

  it("revokes one selected role with one save and refreshes in place", async () => {
    vi.mocked(api.listMemberships).mockResolvedValue([
      {
        id: "membership-active",
        user_id: "user-2",
        company_id: "company-1",
        status: "active",
        default_branch_id: "branch-1",
        has_all_branch_access: false,
        display_name: "Authorized User",
        email: "authorized@example.com",
        branch_name: "Main Branch",
        role_ids: ["role-1"],
        role_codes: ["COMPANY_ADMINISTRATOR"],
      },
    ]);
    const router = renderPage();
    await userEvent.selectOptions(
      await screen.findByRole("combobox", { name: "Active Membership" }),
      "membership-active",
    );
    await userEvent.click(screen.getByRole("checkbox", { name: /Company Administrator/ }));
    await userEvent.click(screen.getByRole("button", { name: "Save access" }));
    expect(api.revokeMembershipRole).toHaveBeenCalledWith(
      "membership-active",
      "role-1",
    );
    expect(api.revokeMembershipRole).toHaveBeenCalledTimes(1);
    expect(refreshAuthorization).toHaveBeenCalledOnce();
    expect(router.state.location.pathname).toBe("/administration");
  });

  it("places authorized Factory Control in the canonical Administration experience", async () => {
    context.permissionCodes = [
      ...(context.permissionCodes ?? []),
      "PLATFORM_FACTORY_CONTROL_READ",
    ];
    renderPage();
    const link = await screen.findByRole("link", { name: "Open Factory Control" });
    expect(link).toHaveAttribute("href", "/administration/factory-control");
  });

  it.each([
    "COMPANY_ROLE_READ",
    "COMPANY_ROLE_MANAGE",
    "COMPANY_PERMISSION_MANAGE",
    "COMPANY_MEMBERSHIP_READ",
  ])("hides role creation and assignment without %s", async (missing) => {
    context.permissionCodes = (context.permissionCodes ?? []).filter(
      (code) => code !== missing,
    );
    renderPage();
    await screen.findByText(/Role Administration|not authorized to administer Company roles/);
    expect(screen.queryByRole("button", { name: "Create role" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save access" })).not.toBeInTheDocument();
  });

  it("renders Company-admin subworkspaces without requesting unauthorized role evidence", async () => {
    context.permissionCodes = ["COMPANY_ADMINISTER"];
    renderPage();

    expect(await screen.findByText("Role administration requires role-read permission.")).toBeInTheDocument();
    expect(screen.getByText("QuickBooks Development sandbox")).toBeInTheDocument();
    expect(screen.getByText("Migration readiness")).toBeInTheDocument();
    expect(api.listRoles).not.toHaveBeenCalled();
    expect(api.listPermissions).not.toHaveBeenCalled();
  });
});
