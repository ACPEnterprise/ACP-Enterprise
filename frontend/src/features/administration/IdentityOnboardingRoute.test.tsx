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

const roles = [["company-admin", "COMPANY_ADMINISTRATOR", "Company Administrator"], ["manager", "OFFICE_MANAGER", "Office Manager"], ["csr", "SERVICE_CSR", "Service CSR"], ["technician", "TECHNICIAN", "Technician"], ["mobile", "ACP_EMPLOYEE_MOBILE", "ACP Employee Mobile"], ["dispatcher", "DISPATCHER", "Dispatcher"], ["field-manager", "FIELD_MANAGER", "Field Manager"]].map(([id, code, name]) => ({ id, code, name, company_id: "company-1", description: null, status: "active", is_system: true }));
const context: AuthenticationContextValue = { status: "authenticated", activeCompany: { id: "company-1", code: "ACP", name: "All County", membership_id: "membership-1", default_branch_id: "main", has_all_branch_access: false, branches: [{ id: "main", code: "MAIN", name: "Main Branch", is_primary: true }] }, permissionCodes: ["COMPANY_IDENTITY_ONBOARDING_MANAGE"], user: null, signIn: vi.fn(), signOut: vi.fn(), signOutAll: vi.fn(), refreshAuthorization: vi.fn(), requireReauthentication: vi.fn() };

function renderPage(authentication = context, entry = "/administration/identity-onboarding") {
  const router = createMemoryRouter([{ path: "/administration/identity-onboarding", Component: IdentityOnboardingRoute }], { initialEntries: [entry] });
  render(<AuthenticationContext.Provider value={authentication}><RouterProvider router={router} /></AuthenticationContext.Provider>);
}

async function fillFiveFields(email = "lianne@example.com") {
  const user = userEvent.setup();
  renderPage();
  await user.type(await screen.findByLabelText("First name"), "Lianne");
  await user.type(screen.getByLabelText("Last name"), "Hernandez");
  await user.type(screen.getByLabelText("Email Address"), email);
  await user.type(screen.getByLabelText("Phone Number"), "555-555-0100");
  return user;
}

describe("IdentityOnboardingRoute", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.listRoles).mockResolvedValue(roles);
    vi.mocked(api.getCanonicalRoleSyncPlan).mockResolvedValue({ company_id: "company-1", plan_digest: "a".repeat(64), safe_to_apply: true, items: [] });
    vi.mocked(api.matchSimpleEmployee).mockResolvedValue({ outcome: "NONE", candidates: [] });
    vi.mocked(api.onboardSimpleEmployee).mockResolvedValue({ onboarding_request_id: "request-1", employee_id: "employee-1", membership_id: "membership-2", branch_id: "main", status: "invited", invitation_eligible: true });
    vi.mocked(api.getIdentityOnboardingDelivery).mockResolvedValue({ request_id: "request-1", invitation_id: "invitation-1", message_id: "message-1", invitation_status: "active", delivery_status: "submitted", template_version: "identity-onboarding-invitation-v1", retry_count: 0, provider_reference_present: true, last_error_code: null, created_at: "2026-09-10T00:00:00Z", submitted_at: "2026-09-10T00:00:01Z", delivered_at: null });
    vi.mocked(workforceApi.getRealRosterOnboardingPreview).mockResolvedValue({ roster_key: "melvin-santiago", display_name: "Melvin Santiago", first_name: "Melvin", last_name: "Santiago", operating_role: "FIELD_TECH", required_role_codes: ["ACP_EMPLOYEE_MOBILE", "TECHNICIAN"], source_employee_id: "pro_23be6c33b14a4127bd737529180a56a1", source_login_email: "koqui360@gmail.com", proposed_login_email: "koqui360@gmail.com", source_branch_id: "main", source_branch_code: "MAIN", source_candidate_employee_id: "employee-melvin", source_disposition: "CREATE_ENTERPRISE_EMPLOYEE_CANDIDATE", safe_to_apply: true, blockers: [] });
    vi.mocked(workforceApi.onboardRealRosterEmployee).mockResolvedValue({ id: "request-source", employee_id: "employee-melvin", membership_id: "membership-melvin", branch_id: "main", masked_login: "k***@gmail.com", status: "invited" });
  });

  it("creates and invites an Employee from exactly five human fields", async () => {
    const user = await fillFiveFields();
    expect(screen.getByLabelText("Position")).toHaveValue("Technician");
    expect(screen.getByText((_, element) => element?.tagName === "P" && element.textContent?.includes("Main Branch") === true && element.textContent.includes("inherited from Company context"))).toBeInTheDocument();
    expect(screen.queryByText(/pay rate|W-4|direct deposit account|permission matrix/i)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add Employee & Send Invite" }));
    expect(api.onboardSimpleEmployee).toHaveBeenCalledWith(expect.objectContaining({ branch_id: "main", phone: "555-555-0100", access_profile: "FIELD_TECHNICIAN" }));
    expect(await screen.findByText("Lianne Hernandez added.")).toBeInTheDocument();
    expect(screen.getByText(/Invitation sent to: lianne@example.com/)).toBeInTheDocument();
    expect(screen.getByText("Payroll Setup")).toBeInTheDocument();
    expect(screen.getAllByText("Not started")).toHaveLength(2);
  });

  it("offers configurable human positions while applying governed templates", async () => {
    renderPage();
    const position = await screen.findByLabelText("Position");
    for (const label of ["Owner", "Operations Manager", "Field Service Manager", "Technician", "Helper"]) expect(position).toHaveTextContent(label);
    await userEvent.selectOptions(position, "Helper");
    expect(position).toHaveValue("Helper");
  });

  it("requires phone but does not require Payroll setup", async () => {
    const user = userEvent.setup(); renderPage();
    await user.type(await screen.findByLabelText("First name"), "Alex");
    await user.type(screen.getByLabelText("Last name"), "Donahue");
    await user.type(screen.getByLabelText("Email Address"), "alex@example.com");
    expect(screen.getByRole("button", { name: "Add Employee & Send Invite" })).toBeDisabled();
  });

  it("handles an existing Employee history without creating a duplicate", async () => {
    vi.mocked(api.matchSimpleEmployee).mockResolvedValue({ outcome: "SINGLE", candidates: [{ employee_id: "employee-linked", source_system: "HOUSECALL_PRO", source_employee_id: "source-1" }] });
    const user = await fillFiveFields("alex@example.com");
    await user.click(screen.getByRole("button", { name: "Add Employee & Send Invite" }));
    expect(await screen.findByText("This person already has a TwelveHats Employee history")).toBeInTheDocument();
    expect(screen.getByText(/Terminated history is never silently reactivated/)).toBeInTheDocument();
    expect(api.onboardSimpleEmployee).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Review & Link Existing Employee" })).toBeInTheDocument();
  });

  it("fails closed on ambiguous protected identity history", async () => {
    vi.mocked(api.matchSimpleEmployee).mockResolvedValue({ outcome: "AMBIGUOUS", candidates: [{ employee_id: "employee-1", source_system: null, source_employee_id: null }, { employee_id: "employee-2", source_system: null, source_employee_id: null }] });
    const user = await fillFiveFields();
    await user.click(screen.getByRole("button", { name: "Add Employee & Send Invite" }));
    expect(await screen.findByText("More than one Employee history needs review")).toBeInTheDocument();
    expect(api.onboardSimpleEmployee).not.toHaveBeenCalled();
  });

  it("preserves exact source identity and still requires the five fields", async () => {
    const user = userEvent.setup();
    renderPage(context, "/administration/identity-onboarding?roster=melvin-santiago");
    expect(await screen.findByLabelText("First name")).toHaveValue("Melvin");
    expect(screen.getByLabelText("Email Address")).toHaveValue("koqui360@gmail.com");
    await user.type(screen.getByLabelText("Phone Number"), "555-555-0111");
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Confirm Source & Send Invite" }));
    expect(workforceApi.onboardRealRosterEmployee).toHaveBeenCalledWith("melvin-santiago", expect.objectContaining({ confirmed_source_employee_id: "pro_23be6c33b14a4127bd737529180a56a1" }));
  });

  it("fails closed without onboarding authority", () => {
    renderPage({ ...context, permissionCodes: [] });
    expect(screen.getByText("You are not authorized to add employees.")).toBeInTheDocument();
    expect(api.listRoles).not.toHaveBeenCalled();
  });
});
