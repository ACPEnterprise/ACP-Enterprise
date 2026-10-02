import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as workforceApi from "../../api/workforce";
import { AuthenticationContext, type AuthenticationContextValue } from "../../auth/AuthenticationContext";
import * as api from "./api";
import { IdentityOnboardingRoute } from "./IdentityOnboardingRoute";
vi.mock("./api");
vi.mock("../../api/workforce");
const roles = [["company-admin", "COMPANY_ADMINISTRATOR", "Company Administrator"], ["manager", "OFFICE_MANAGER", "Office Manager"], ["csr", "SERVICE_CSR", "Service CSR"], ["technician", "TECHNICIAN", "Technician"], ["mobile", "ACP_EMPLOYEE_MOBILE", "ACP Employee Mobile"]].map(([id, code, name]) => ({ id, code, name, company_id: "company-1", description: null, status: "active", is_system: true }));
const context: AuthenticationContextValue = { status: "authenticated", activeCompany: { id: "company-1", code: "ACP", name: "All County", membership_id: "membership-1", default_branch_id: "main", has_all_branch_access: false, branches: [{ id: "main", code: "MAIN", name: "Main Branch", is_primary: true }] }, permissionCodes: ["COMPANY_IDENTITY_ONBOARDING_MANAGE"], user: null, signIn: vi.fn(), signOut: vi.fn(), signOutAll: vi.fn(), refreshAuthorization: vi.fn(), requireReauthentication: vi.fn() };
function renderPage(authentication = context, entry = "/administration/identity-onboarding") { const router = createMemoryRouter([{ path: "/administration/identity-onboarding", Component: IdentityOnboardingRoute }], { initialEntries: [entry] }); render(<AuthenticationContext.Provider value={authentication}><RouterProvider router={router} /></AuthenticationContext.Provider>); }
describe("IdentityOnboardingRoute", () => {
  beforeEach(() => {
    vi.clearAllMocks(); vi.mocked(api.listRoles).mockResolvedValue(roles);
    vi.mocked(api.getCanonicalRoleSyncPlan).mockResolvedValue({ company_id: "company-1", plan_digest: "a".repeat(64), safe_to_apply: true, items: [] });
    vi.mocked(api.applyCanonicalRoleSync).mockResolvedValue({ plan: { company_id: "company-1", plan_digest: "a".repeat(64), safe_to_apply: true, items: [] }, roles_created: [], permissions_added: [], metadata_restored: [], authorization_users_advanced: 0 });
    vi.mocked(api.matchSimpleEmployee).mockResolvedValue({ outcome: "NONE", candidates: [] });
    vi.mocked(api.onboardSimpleEmployee).mockResolvedValue({ onboarding_request_id: "request-1", employee_id: "employee-1", membership_id: "membership-2", branch_id: "main", status: "invited", invitation_eligible: true });
    vi.mocked(api.initiateEmployeeBetaOnboarding).mockResolvedValue({ id: "request-1", employee_id: "employee-1", membership_id: "membership-2", branch_id: "main", masked_login: "l***@example.com", status: "invited" });
    vi.mocked(api.getIdentityOnboardingDelivery).mockResolvedValue({ request_id: "request-1", invitation_id: "invitation-1", message_id: "message-1", invitation_status: "active", delivery_status: "submitted", template_version: "identity-onboarding-invitation-v1", retry_count: 0, provider_reference_present: true, last_error_code: null, created_at: "2026-09-10T00:00:00Z", submitted_at: "2026-09-10T00:00:01Z", delivered_at: null });
    vi.mocked(workforceApi.getRealRosterOnboardingPreview).mockResolvedValue({ roster_key: "melvin-santiago", display_name: "Melvin Santiago", first_name: "Melvin", last_name: "Santiago", operating_role: "FIELD_TECH", required_role_codes: ["ACP_EMPLOYEE_MOBILE", "TECHNICIAN"], source_employee_id: "pro_23be6c33b14a4127bd737529180a56a1", source_login_email: "koqui360@gmail.com", proposed_login_email: "koqui360@gmail.com", source_branch_id: "main", source_branch_code: "MAIN", source_candidate_employee_id: "employee-melvin", source_disposition: "CREATE_ENTERPRISE_EMPLOYEE_CANDIDATE", safe_to_apply: true, blockers: [] });
    vi.mocked(workforceApi.onboardRealRosterEmployee).mockResolvedValue({ id: "request-source", employee_id: "employee-melvin", membership_id: "membership-melvin", branch_id: "main", masked_login: "k***@gmail.com", status: "invited" });
  });
  it("sends one standard Technician invite without exposing infrastructure", async () => {
    const user = userEvent.setup(); renderPage();
    await user.type(await screen.findByLabelText("First name"), "Lianne"); await user.type(screen.getByLabelText("Last name"), "Hernandez"); await user.type(screen.getByLabelText("Email"), "lianne@example.com");
    const [role, branch] = screen.getAllByRole("combobox");
    expect(role).toHaveValue("FIELD_TECH"); expect(branch).toHaveValue("main");
    expect(screen.queryByText(/Membership UUID/i)).not.toBeInTheDocument(); expect(screen.queryByText(/Effective permission preview/i)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Send Invite" }));
    expect(api.matchSimpleEmployee).toHaveBeenCalledWith(expect.objectContaining({ branch_id: "main", email: "lianne@example.com" }));
    expect(api.onboardSimpleEmployee).toHaveBeenCalledWith(expect.objectContaining({ access_profile: "FIELD_TECHNICIAN", branch_id: "main" })); expect(await screen.findByText("Employee invited. Delivery status is shown below.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View Team" })).toHaveAttribute("href", "/employees");
  });
  it("shows only the four approved owner-facing operating profiles", async () => {
    renderPage(); const select = (await screen.findAllByRole("combobox"))[0];
    for (const label of ["ADMIN", "OFFICE MANAGER", "OFFICE STAFF", "FIELD TECH"]) expect(select).toHaveTextContent(label);
    expect(select).not.toHaveTextContent("SUPPORT"); expect(select).not.toHaveTextContent("ACP EMPLOYEE MOBILE");
  });
  it("prefills owner-confirmed roster facts but never invents login email", async () => {
    renderPage(context, "/administration/identity-onboarding?name=Melvin%20Santiago&profile=FIELD_TECH&branch=MAIN");
    expect(await screen.findByLabelText("First name")).toHaveValue("Melvin");
    expect(screen.getByLabelText("Last name")).toHaveValue("Santiago");
    expect(screen.getByLabelText("Email")).toHaveValue("");
    expect((await screen.findAllByRole("combobox"))[0]).toHaveValue("FIELD_TECH");
  });
  it("locks preserved source facts and sends one source-backed invitation after access confirmation", async () => {
    const user = userEvent.setup();
    renderPage(context, "/administration/identity-onboarding?roster=melvin-santiago");
    expect(await screen.findByLabelText("First name")).toHaveValue("Melvin");
    expect(screen.getByLabelText("Email")).toHaveValue("koqui360@gmail.com");
    expect(screen.getByLabelText("Email")).not.toHaveAttribute("readonly");
    expect(screen.getByText(/HCP pro_23be6c33b14a4127bd737529180a56a1/)).toBeVisible();
    await user.clear(screen.getByLabelText("Email"));
    await user.type(screen.getByLabelText("Email"), "owner-confirmed@example.com");
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Confirm Source & Send Invite" }));
    expect(workforceApi.onboardRealRosterEmployee).toHaveBeenCalledTimes(1);
    expect(workforceApi.onboardRealRosterEmployee).toHaveBeenCalledWith("melvin-santiago", {
      confirmed_source_employee_id: "pro_23be6c33b14a4127bd737529180a56a1",
      confirmed_login_email: "owner-confirmed@example.com",
      confirm_access_profile: true,
    });
    expect(api.initiateEmployeeBetaOnboarding).not.toHaveBeenCalled();
    expect(await screen.findByText("Source Employee bound and invited. Delivery status is shown below.")).toBeVisible();
  });
  it("does not mutate when identity planning finds a conflict", async () => {
    vi.mocked(api.matchSimpleEmployee).mockResolvedValue({ outcome: "AMBIGUOUS", candidates: [{ employee_id: "employee-1", source_system: "HOUSECALL_PRO", source_employee_id: "source-1" }, { employee_id: "employee-2", source_system: null, source_employee_id: null }] });
    const user = userEvent.setup(); renderPage(); await user.type(await screen.findByLabelText("First name"), "Lianne"); await user.type(screen.getByLabelText("Last name"), "Hernandez"); await user.type(screen.getByLabelText("Email"), "lianne@example.com"); await user.click(screen.getByRole("button", { name: "Send Invite" }));
    expect(await screen.findByText(/multiple existing employee records/i)).toBeInTheDocument(); expect(api.onboardSimpleEmployee).not.toHaveBeenCalled();
  });
  it("asks before linking a single existing employee history", async () => {
    vi.mocked(api.matchSimpleEmployee).mockResolvedValue({ outcome: "SINGLE", candidates: [{ employee_id: "employee-linked", source_system: "HOUSECALL_PRO", source_employee_id: "source-1" }] });
    vi.mocked(api.onboardSimpleEmployee).mockResolvedValue({ onboarding_request_id: "request-linked", employee_id: "employee-linked", membership_id: "membership-1", branch_id: "main", status: "active", invitation_eligible: false });
    const user = userEvent.setup(); renderPage();
    await user.type(await screen.findByLabelText("First name"), "Alex"); await user.type(screen.getByLabelText("Last name"), "Donahue"); await user.type(screen.getByLabelText("Email"), "alex@example.com");
    await user.click(screen.getByRole("button", { name: "Send Invite" }));
    expect(await screen.findByText("Existing employee history found")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Link & Continue" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Link & Continue" }));
    expect(api.onboardSimpleEmployee).toHaveBeenCalledWith(expect.objectContaining({ email: "alex@example.com", access_profile: "FIELD_TECHNICIAN" }));
    expect(await screen.findByText("Employee created/linked")).toBeInTheDocument();
  });
  it("fails closed without onboarding authority", () => { renderPage({ ...context, permissionCodes: [] }); expect(screen.getByText("You are not authorized to add employees.")).toBeInTheDocument(); expect(api.listRoles).not.toHaveBeenCalled(); });
  it("repairs safely missing canonical profiles through the audited reconciliation", async () => {
    const user = userEvent.setup();
    vi.mocked(api.listRoles)
      .mockResolvedValueOnce(roles.filter((role) => role.code !== "ACP_EMPLOYEE_MOBILE"))
      .mockResolvedValueOnce(roles);
    renderPage({ ...context, permissionCodes: [...(context.permissionCodes ?? []), "COMPANY_PERMISSION_MANAGE"] });
    expect(await screen.findByText(/canonical role reconciliation: FIELD TECH/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Prepare approved profiles" }));
    expect(api.applyCanonicalRoleSync).toHaveBeenCalledWith("a".repeat(64));
    expect(await screen.findByText("Approved Employee operating profiles are ready.")).toBeInTheDocument();
    const select = (await screen.findAllByRole("combobox"))[0];
    expect(select).toHaveTextContent("FIELD TECH");
  });
  it("does not replace a conflicting protected role", async () => {
    vi.mocked(api.listRoles).mockResolvedValue(roles.filter((role) => role.code !== "OFFICE_MANAGER"));
    vi.mocked(api.getCanonicalRoleSyncPlan).mockResolvedValue({
      company_id: "company-1",
      plan_digest: "b".repeat(64),
      safe_to_apply: false,
      items: [{ code: "OFFICE_MANAGER", classification: "UNSAFE_IDENTITY_COLLISION", missing_permissions: [], metadata_update_required: false }],
    });
    renderPage({ ...context, permissionCodes: [...(context.permissionCodes ?? []), "COMPANY_PERMISSION_MANAGE"] });
    expect(await screen.findByText(/protected role identity conflict requires review/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Prepare approved profiles" })).not.toBeInTheDocument();
    expect(api.applyCanonicalRoleSync).not.toHaveBeenCalled();
  });
});
