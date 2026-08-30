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
  });

  it("submits the protected address in a POST body bound to the beta identity", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.type(
      await screen.findByLabelText("Employee login address"),
      "synthetic@example.invalid",
    );
    await user.click(screen.getByRole("button", { name: "Create beta onboarding" }));

    expect(api.initiateEmployeeBetaOnboarding).toHaveBeenCalledWith({
      request_key: "acp-employee-beta-v1",
      branch_id: "branch-1",
      first_name: "ACP Employee",
      last_name: "Beta",
      display_name: "ACP Employee Beta",
      employee_type: "employee",
      employee_number_prefix: "EMP-",
      employee_number_width: 4,
      role_ids: ["employee-role"],
      login_email: "synthetic@example.invalid",
    });
    expect(await screen.findByText(/Onboarding was created/)).toBeInTheDocument();
    expect(screen.queryByDisplayValue("synthetic@example.invalid")).not.toBeInTheDocument();
  });

  it("fails closed without onboarding authority", () => {
    renderPage({ ...context, permissionCodes: [] });
    expect(
      screen.getByText("You are not authorized to initiate Company identity onboarding."),
    ).toBeInTheDocument();
    expect(api.listRoles).not.toHaveBeenCalled();
  });

  it("does not permit onboarding through an unqualified Employee role", async () => {
    vi.mocked(api.listPermissions).mockResolvedValue(requiredPermissions.slice(0, 3));
    renderPage();
    expect(
      await screen.findByText(
        "The canonical Company Employee role is not ready for ACP Employee onboarding.",
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
