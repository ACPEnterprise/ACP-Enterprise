import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthenticationContext, type AuthenticationContextValue } from "../../auth/AuthenticationContext";
import * as api from "./api";
import { IdentityOnboardingRoute } from "./IdentityOnboardingRoute";
vi.mock("./api");
const roles = [["company-admin", "COMPANY_ADMINISTRATOR", "Company Administrator"], ["manager", "OFFICE_MANAGER", "Office Manager"], ["csr", "SERVICE_CSR", "Service CSR"], ["technician", "TECHNICIAN", "Technician"]].map(([id, code, name]) => ({ id, code, name, company_id: "company-1", description: null, status: "active", is_system: true }));
const context: AuthenticationContextValue = { status: "authenticated", activeCompany: { id: "company-1", code: "ACP", name: "All County", membership_id: "membership-1", default_branch_id: "main", has_all_branch_access: false, branches: [{ id: "main", code: "MAIN", name: "Main Branch", is_primary: true }] }, permissionCodes: ["COMPANY_IDENTITY_ONBOARDING_MANAGE"], user: null, signIn: vi.fn(), signOut: vi.fn(), signOutAll: vi.fn(), requireReauthentication: vi.fn() };
function renderPage(authentication = context) { const router = createMemoryRouter([{ path: "/administration/identity-onboarding", Component: IdentityOnboardingRoute }], { initialEntries: ["/administration/identity-onboarding"] }); render(<AuthenticationContext.Provider value={authentication}><RouterProvider router={router} /></AuthenticationContext.Provider>); }
describe("IdentityOnboardingRoute", () => {
  beforeEach(() => {
    vi.clearAllMocks(); vi.mocked(api.listRoles).mockResolvedValue(roles);
    vi.mocked(api.planEmployeeOnboarding).mockResolvedValue({ classification: "NEW_EMPLOYEE_CANDIDATE", safe_to_apply: true, masked_login: "l***@example.com", user_action: "CREATE_USER", membership_action: "CREATE_MEMBERSHIP", employee_action: "CREATE_EMPLOYEE", branch_action: "GRANT_EXPLICIT_BRANCH", employee_number_prefix: "ACP-", employee_number_width: 4, role_codes: ["TECHNICIAN"], additional_permission_codes: [], readiness_stages: { IDENTITY: "READY" }, blockers: [] });
    vi.mocked(api.initiateEmployeeBetaOnboarding).mockResolvedValue({ id: "request-1", employee_id: "employee-1", membership_id: "membership-2", branch_id: "main", masked_login: "l***@example.com", status: "invited" });
    vi.mocked(api.getIdentityOnboardingDelivery).mockResolvedValue({ request_id: "request-1", invitation_id: "invitation-1", message_id: "message-1", invitation_status: "active", delivery_status: "submitted", template_version: "identity-onboarding-invitation-v1", retry_count: 0, provider_reference_present: true, last_error_code: null, created_at: "2026-09-10T00:00:00Z", submitted_at: "2026-09-10T00:00:01Z", delivered_at: null });
  });
  it("sends one standard Technician invite without exposing infrastructure", async () => {
    const user = userEvent.setup(); renderPage();
    await user.type(await screen.findByLabelText("First name"), "Lianne"); await user.type(screen.getByLabelText("Last name"), "Hernandez"); await user.type(screen.getByLabelText("Email"), "lianne@example.com");
    const [role, branch] = screen.getAllByRole("combobox");
    expect(role).toHaveValue("technician"); expect(branch).toHaveValue("main");
    expect(screen.queryByText(/Membership UUID/i)).not.toBeInTheDocument(); expect(screen.queryByText(/Effective permission preview/i)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Send Invite" }));
    expect(api.planEmployeeOnboarding).toHaveBeenCalledWith(expect.objectContaining({ role_ids: ["technician"], additional_permission_ids: [], branch_id: "main" }));
    expect(api.initiateEmployeeBetaOnboarding).toHaveBeenCalledTimes(1); expect(await screen.findByText("Employee invited. Delivery status is shown below.")).toBeInTheDocument();
  });
  it("shows only the five standard owner-facing role choices", async () => {
    renderPage(); const select = (await screen.findAllByRole("combobox"))[0];
    for (const label of ["OWNER", "MANAGER", "ADMIN", "CSR", "TECHNICIAN"]) expect(select).toHaveTextContent(label);
    expect(select).not.toHaveTextContent("SUPPORT"); expect(select).not.toHaveTextContent("ACP_EMPLOYEE_MOBILE");
  });
  it("does not mutate when identity planning finds a conflict", async () => {
    vi.mocked(api.planEmployeeOnboarding).mockResolvedValue({ classification: "DUPLICATE_CONFLICT", safe_to_apply: false, masked_login: "l***@example.com", user_action: "REUSE_REVIEW_REQUIRED", membership_action: "NO_CHANGE", employee_action: "NO_CHANGE", branch_action: "NO_CHANGE", employee_number_prefix: "ACP-", employee_number_width: 4, role_codes: ["TECHNICIAN"], additional_permission_codes: [], readiness_stages: { IDENTITY: "REVIEW_REQUIRED" }, blockers: ["employee_identity_already_exists"] });
    const user = userEvent.setup(); renderPage(); await user.type(await screen.findByLabelText("First name"), "Lianne"); await user.type(screen.getByLabelText("Last name"), "Hernandez"); await user.type(screen.getByLabelText("Email"), "lianne@example.com"); await user.click(screen.getByRole("button", { name: "Send Invite" }));
    expect(await screen.findByText(/needs review.*employee identity already exists/i)).toBeInTheDocument(); expect(api.initiateEmployeeBetaOnboarding).not.toHaveBeenCalled();
  });
  it("fails closed without onboarding authority", () => { renderPage({ ...context, permissionCodes: [] }); expect(screen.getByText("You are not authorized to add employees.")).toBeInTheDocument(); expect(api.listRoles).not.toHaveBeenCalled(); });
});
