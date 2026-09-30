import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import * as workforceHooks from "../../hooks/useWorkforce";
import { RealRosterActivationConsole } from "./RealRosterActivationConsole";

vi.mock("../../hooks/useWorkforce");
vi.mock("../../auth", () => ({
  useAuth: () => ({
    permissionCodes: ["COMPANY_WORKFORCE_CAPABILITY_MANAGE"],
    activeCompany: { branches: [{ id: "branch-main", code: "MAIN", name: "MAIN" }] },
  }),
}));

describe("RealRosterActivationConsole", () => {
  it("requires a reason and records readiness for the exact bound technician", async () => {
    const mutate = vi.fn();
    vi.mocked(workforceHooks.useRealRosterReadiness).mockReturnValue({
      canBind: true,
      bind: { isPending: false, mutate: vi.fn() },
      prepareFieldReadiness: { isPending: false, mutate },
      query: { isLoading: false, isError: false, data: { total: 8, bound: 1, field_tech_total: 5, field_tech_capability_ready: 1, items: [{
        roster_key: "melvin-santiago", display_name: "Melvin Santiago", operating_role: "FIELD_TECH", field_tech: true,
        source_employee_id: "pro_melvin", source_login_email: "melvin@example.com", source_admission: "SAFE_CREATE", source_onboarding_state: "ALREADY_BOUND", source_candidate_employee_id: "employee-melvin",
        employee_id: "employee-melvin", employee_display_name: "Melvin Santiago", user_state: "USER_READY", employee_state: "EMPLOYEE_READY",
        membership_state: "MEMBERSHIP_READY", branch_state: "MAIN_BRANCH_READY", role_state: "ROLE_READY", workforce_profile_state: "WORKFORCE_PROFILE_READY",
        technician_capability_state: "TECHNICIAN_CAPABILITY_READY", mobile_state: "MOBILE_READY", credential_state: "ACP_LOGIN_READY",
        availability_state: "EXPLICIT_WINDOW_REQUIRED", dispatch_state: "READY_FOR_WINDOW_EVALUATION", timekeeping_state: "LINKED",
        payroll_linkage_state: "LINKED_INPUTS_NOT_EVALUATED", identity_confirmed_at: "2026-09-15T00:00:00Z",
        readiness_window_start_at: null, readiness_window_end_at: null, readiness_source: null, blockers: [],
      }] } },
    } as never);
    const user = userEvent.setup();
    render(<MemoryRouter><RealRosterActivationConsole /></MemoryRouter>);
    expect(screen.getByText("Identity and access ready")).toBeVisible();
    expect(screen.getByText("Timekeeping handoff")).toBeVisible();
    expect(screen.getByText("LINKED")).toBeVisible();
    expect(screen.getByText("LINKED INPUTS NOT EVALUATED")).toBeVisible();
    expect(screen.getByRole("link", { name: "Open access, capabilities and history" })).toHaveAttribute("href", "/employees?employee=employee-melvin");
    const action = screen.getByRole("button", { name: "Record this employee’s bounded readiness" });
    expect(action).toBeDisabled();
    const [start, end] = screen.getAllByDisplayValue("");
    fireEvent.change(start, { target: { value: "2026-09-16T08:00" } });
    fireEvent.change(end, { target: { value: "2026-09-16T17:00" } });
    await user.type(screen.getByPlaceholderText("Confirmed operating window"), "Owner confirmed field shift");
    await user.click(action);
    expect(mutate).toHaveBeenCalledWith(expect.objectContaining({ employeeId: "employee-melvin", branchId: "branch-main", reason: "Owner confirmed field shift" }));
  });

  it("offers only server-authorized real candidates and links source-backed onboarding", () => {
    vi.mocked(workforceHooks.useRealRosterReadiness).mockReturnValue({
      canBind: true,
      bind: { isPending: false, mutate: vi.fn() },
      prepareFieldReadiness: { isPending: false, mutate: vi.fn() },
      query: { isLoading: false, isError: false, data: {
        total: 8, bound: 0, field_tech_total: 5, field_tech_capability_ready: 0,
        binding_candidate_count: 1,
        binding_candidates: [{ employee_id: "employee-melvin", employee_number: "HCP-0002", display_name: "Melvin Santiago", employment_status: "inactive", home_branch_id: "branch-main" }],
        source_evidence: [], items: [{
          roster_key: "melvin-santiago", display_name: "Melvin Santiago", operating_role: "FIELD_TECH", field_tech: true,
          source_employee_id: "pro_23be6c33b14a4127bd737529180a56a1", source_login_email: "koqui360@gmail.com", source_admission: "SAFE_CREATE", source_onboarding_state: "READY_TO_ONBOARD", source_candidate_employee_id: "employee-melvin",
          employee_id: null, employee_display_name: null, employment_status: null, user_state: "AUTHENTICATED_VERIFICATION_REQUIRED", employee_state: "AUTHENTICATED_VERIFICATION_REQUIRED",
          membership_state: "AUTHENTICATED_VERIFICATION_REQUIRED", branch_state: "AUTHENTICATED_VERIFICATION_REQUIRED", role_state: "AUTHENTICATED_VERIFICATION_REQUIRED", workforce_profile_state: "AUTHENTICATED_VERIFICATION_REQUIRED",
          technician_capability_state: "NOT_APPLICABLE", mobile_state: "AUTHENTICATED_VERIFICATION_REQUIRED", credential_state: "AUTHENTICATED_VERIFICATION_REQUIRED",
          availability_state: "AUTHENTICATED_VERIFICATION_REQUIRED", dispatch_state: "AUTHENTICATED_VERIFICATION_REQUIRED", timekeeping_state: "AUTHENTICATED_VERIFICATION_REQUIRED",
          payroll_linkage_state: "AUTHENTICATED_VERIFICATION_REQUIRED", identity_confirmed_at: null, readiness_window_start_at: null,
          readiness_window_end_at: null, readiness_source: null, blockers: ["OWNER_EMPLOYEE_BINDING_REQUIRED"],
        }],
      } },
    } as never);
    render(<MemoryRouter><RealRosterActivationConsole /></MemoryRouter>);
    expect(screen.getByRole("option", { name: "Melvin Santiago · HCP-0002" })).toBeVisible();
    expect(screen.queryByText(/Synthetic Beta Employee/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review source & send invite" })).toHaveAttribute(
      "href",
      "/administration/identity-onboarding?roster=melvin-santiago",
    );
  });
});
