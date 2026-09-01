import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  AuthenticationContext,
  type AuthenticationContextValue,
} from "../../auth/AuthenticationContext";
import * as api from "./api";
import { IdentityOnboardingRoute } from "./IdentityOnboardingRoute";

vi.mock("./api");

const employeeRole = {
  id: "employee-role",
  company_id: "company-1",
  code: "COMPANY_USER",
  name: "Company User",
  description: null,
  status: "active",
  is_system: true,
};

const requiredPermissions = [
  "COMPANY_TIMEKEEPING_OWN_READ",
  "COMPANY_TIMEKEEPING_OWN_PUNCH",
  "COMPANY_EMPLOYEE_OPERATIONS_OWN_DAY_READ",
  "COMPANY_JOB_READ",
].map((code) => ({
  id: code,
  code,
  name: code,
  description: null,
  scope: "company",
  active: true,
  assignable: true,
  assigned: true,
  reconciliation_required: false,
  category: code.includes("TIMEKEEPING") ? "Timekeeping" : "Jobs",
  access_nature: code.includes("READ") ? "READ_ONLY" as const : "MUTATION" as const,
  own_data: code.includes("_OWN_"),
  high_impact: false,
}));

const context: AuthenticationContextValue = {
  status: "authenticated",
  activeCompany: {
    id: "company-1",
    code: "PREVIEW",
    name: "Preview Company",
    membership_id: "membership-1",
    default_branch_id: "branch-1",
    has_all_branch_access: false,
    branches: [
      { id: "branch-1", code: "MAIN", name: "Main", is_primary: true },
    ],
  },
  permissionCodes: ["COMPANY_IDENTITY_ONBOARDING_MANAGE"],
  user: null,
  signIn: vi.fn(),
  signOut: vi.fn(),
  signOutAll: vi.fn(),
  requireReauthentication: vi.fn(),
};

function renderPage(authentication = context) {
  const router = createMemoryRouter(
    [{ path: "/administration/identity-onboarding", Component: IdentityOnboardingRoute }],
    { initialEntries: ["/administration/identity-onboarding"] },
  );
  render(
    <AuthenticationContext.Provider value={authentication}>
      <RouterProvider router={router} />
    </AuthenticationContext.Provider>,
  );
}

describe("IdentityOnboardingRoute", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.listRoles).mockResolvedValue([employeeRole]);
    vi.mocked(api.listPermissions).mockResolvedValue(requiredPermissions);
    vi.mocked(api.initiateEmployeeBetaOnboarding).mockResolvedValue({
      id: "request-1",
      employee_id: "employee-1",
      membership_id: "membership-2",
      branch_id: "branch-1",
      masked_login: "s***@example.invalid",
      status: "invited",
    });
    vi.mocked(api.getIdentityOnboardingDelivery).mockResolvedValue({
      request_id: "request-1",
      invitation_id: "invitation-1",
      message_id: "message-1",
      invitation_status: "active",
      delivery_status: "provider_not_configured",
      template_version: "employee-invitation-v1",
      retry_count: 0,
      provider_reference_present: false,
      last_error_code: "PROVIDER_NOT_CONFIGURED",
      created_at: "2026-09-01T00:00:00Z",
      submitted_at: null,
      delivered_at: null,
    });
  });

  it("prepares a protected Employee identity with an explicit Branch and role", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.type(
      await screen.findByLabelText("Employee login address"),
      "synthetic@example.invalid",
    );
    await user.type(screen.getByLabelText("First name"), "Synthetic");
    await user.type(screen.getByLabelText("Last name"), "Technician");
    await user.click(screen.getByRole("button", { name: "Prepare Employee onboarding" }));

    expect(api.initiateEmployeeBetaOnboarding).toHaveBeenCalledWith(expect.objectContaining({
      branch_id: "branch-1",
      first_name: "Synthetic",
      last_name: "Technician",
      display_name: "Synthetic Technician",
      employee_type: "employee",
      employee_number_prefix: "EMP-",
      employee_number_width: 4,
      role_ids: ["employee-role"],
      login_email: "synthetic@example.invalid",
    }));
    expect(vi.mocked(api.initiateEmployeeBetaOnboarding).mock.calls[0]?.[0].request_key).toMatch(/^employee-admin-/);
    expect(await screen.findByText(/Onboarding was created/)).toBeInTheDocument();
    expect(await screen.findByText("provider not configured", { exact: true })).toBeInTheDocument();
    expect(screen.getByText("Provider not configured or not accepted")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("synthetic@example.invalid")).not.toBeInTheDocument();
  });

  it("fails closed without onboarding authority", () => {
    renderPage({ ...context, permissionCodes: [] });
    expect(
      screen.getByText("You are not authorized to initiate Company identity onboarding."),
    ).toBeInTheDocument();
    expect(api.listRoles).not.toHaveBeenCalled();
  });

  it("does not permit onboarding without an active canonical role", async () => {
    vi.mocked(api.listRoles).mockResolvedValue([]);
    renderPage();
    expect(
      await screen.findByText(
        "Canonical Employee roles are unavailable.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Employee login address")).not.toBeInTheDocument();
  });

  it("recovers readiness after a temporary API failure", async () => {
    const user = userEvent.setup();
    vi.mocked(api.listRoles)
      .mockRejectedValueOnce(new Error("temporary unavailable"))
      .mockResolvedValueOnce([employeeRole]);
    renderPage();
    expect(
      await screen.findByText("Employee onboarding readiness could not be verified."),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry readiness" }));
    expect(await screen.findByLabelText("Employee login address")).toBeInTheDocument();
    expect(api.listRoles).toHaveBeenCalledTimes(2);
  });
});
