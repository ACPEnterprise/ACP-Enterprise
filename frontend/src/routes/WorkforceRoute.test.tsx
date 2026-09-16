import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import * as workforceHooks from "../hooks/useWorkforce";
import { WorkforceRoute } from "./WorkforceRoute";

vi.mock("../hooks/useWorkforce");
vi.mock("../hooks/useWorkdayTime", () => ({
  useAdminTimecardReview: () => ({
    data: undefined,
    isLoading: false,
    isError: false,
  }),
  useTimeCorrection: () => ({
    isPending: false,
    isError: false,
    mutate: vi.fn(),
  }),
  useAdminTimecardOperations: () => ({
    data: undefined,
    isLoading: false,
    isError: false,
  }),
  usePayPeriods: () => ({ data: [], isLoading: false, isError: false }),
}));
vi.mock("../features/administration/hooks", () => ({
  useRoles: () => ({ data: [], isLoading: false, isError: false }),
}));
vi.mock("../auth", () => ({
  useAuth: () => ({
    permissionCodes: [],
    activeCompany: {
      default_branch_id: "branch-1",
      branches: [{ id: "branch-1", name: "MAIN", code: "MAIN" }],
    },
  }),
}));

const summary = {
  employee_id: "employee-1",
  employee_number: "EMP-1",
  display_name: "Marisol Rivera",
  job_title: "Service Technician",
  employee_type: "employee",
  employee_status: "active",
  home_branch_id: "branch-1",
  profile_id: "profile-1",
  profile_status: "active",
  technician: true,
  capability_codes: ["technician", "water_heater"],
  language_codes: ["en", "es"],
  readiness_state: "READY" as const,
  readiness_blockers: [],
  updated_at: "2026-08-30T12:00:00Z",
};

describe("WorkforceRoute", () => {
  function mockEligibility() {
    vi.mocked(workforceHooks.useRealRosterReadiness).mockReturnValue({
      query: {
        isLoading: false,
        isError: false,
        data: {
          total: 8,
          bound: 0,
          field_tech_total: 5,
          field_tech_capability_ready: 0,
          source_evidence: [],
          source_evidence_total: 0,
          source_only_total: 0,
          certification_required_total: 8,
          login_ready_total: 0,
          membership_ready_total: 0,
          branch_ready_total: 0,
          mobile_ready_total: 0,
          dispatch_ready_total: 0,
          timekeeping_ready_total: 0,
          payroll_identity_ready_total: 0,
          items: [{
            roster_key: "melvin-santiago",
            display_name: "Melvin Santiago",
            operating_role: "FIELD_TECH",
            field_tech: true,
            employee_id: null,
            employee_display_name: null,
            user_state: "AUTHENTICATED_VERIFICATION_REQUIRED",
            employee_state: "AUTHENTICATED_VERIFICATION_REQUIRED",
            membership_state: "AUTHENTICATED_VERIFICATION_REQUIRED",
            branch_state: "AUTHENTICATED_VERIFICATION_REQUIRED",
            role_state: "AUTHENTICATED_VERIFICATION_REQUIRED",
            workforce_profile_state: "AUTHENTICATED_VERIFICATION_REQUIRED",
            technician_capability_state: "AUTHENTICATED_VERIFICATION_REQUIRED",
            mobile_state: "AUTHENTICATED_VERIFICATION_REQUIRED",
            credential_state: "AUTHENTICATED_VERIFICATION_REQUIRED",
            availability_state: "AUTHENTICATED_VERIFICATION_REQUIRED",
            dispatch_state: "AUTHENTICATED_VERIFICATION_REQUIRED",
            timekeeping_state: "AUTHENTICATED_VERIFICATION_REQUIRED",
            payroll_linkage_state: "AUTHENTICATED_VERIFICATION_REQUIRED",
            identity_confirmed_at: null,
            readiness_window_start_at: null,
            readiness_window_end_at: null,
            readiness_source: null,
            blockers: ["OWNER_EMPLOYEE_BINDING_REQUIRED"],
          }],
        },
      },
      bind: { isPending: false, mutate: vi.fn() },
      prepareFieldReadiness: { isPending: false, mutate: vi.fn() },
      canBind: false,
    } as never);
    vi.mocked(workforceHooks.useWorkforceEligibility).mockReturnValue({
      isPending: false,
      isError: false,
      data: undefined,
      mutate: vi.fn(),
    } as never);
    vi.mocked(workforceHooks.useEmployeeAdministration).mockReturnValue({
      isLoading: false,
      isError: false,
      data: undefined,
    } as never);
    vi.mocked(workforceHooks.useEmployeeAccessMutation).mockReturnValue({
      isPending: false,
      isError: false,
      mutate: vi.fn(),
    } as never);
    vi.mocked(workforceHooks.useEmployeeTimeline).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        employee_id: "employee-1",
        items: [{
          event_type: "MOBILE_ROLE_ASSIGNED",
          occurred_at: "2026-08-30T12:00:00Z",
          authority: "ACP_NATIVE",
          source: "membership_role",
          actor_user_id: "user-1",
          actor_display_name: "Office Owner",
          description: "ACP Employee Mobile role assigned.",
          employee_id: "employee-1",
          navigation_reference: null,
        }],
      },
    } as never);
  }

  it("provides a visible operational profile without Payroll data", async () => {
    mockEligibility();
    vi.mocked(workforceHooks.useWorkforceDirectory).mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: [summary],
    } as never);
    vi.mocked(workforceHooks.useWorkforceEmployee).mockImplementation(
      (id) =>
        ({
          isLoading: false,
          isError: false,
          data: id
            ? {
                ...summary,
                capabilities: [
                  {
                    code: "technician",
                    display_name: "Technician",
                    proficiency: "qualified",
                    status: "active",
                  },
                ],
                certifications: [
                  {
                    code: "trade",
                    display_name: "Trade credential",
                    credential_reference: "SAFE-REF",
                    status: "active",
                    issued_on: "2026-01-01",
                    expires_on: "2027-01-01",
                  },
                ],
                languages: [
                  {
                    code: "es",
                    english_name: "Spanish",
                    native_name: "Español",
                    spoken_proficiency: "professional",
                    customer_facing_eligible: true,
                    interpreter_verified: false,
                    status: "active",
                  },
                ],
                branches: [
                  {
                    branch_id: "branch-1",
                    status: "active",
                    starts_on: null,
                    ends_on: null,
                  },
                ],
                work_restrictions: [],
                equipment_capabilities: [],
                availability: [],
              }
            : undefined,
        }) as never,
    );
    render(
      <MemoryRouter>
        <WorkforceRoute />
      </MemoryRouter>,
    );
    await userEvent.click(
      screen.getByRole("button", { name: /Marisol Rivera/ }),
    );
    expect(
      screen.getByRole("heading", { name: "Marisol Rivera" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Spanish")).toBeInTheDocument();
    expect(
      screen.getByText(
        (_, node) =>
          node?.tagName === "P" &&
          node.textContent?.includes("professional") === true,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/Trade credential/)).toBeInTheDocument();
    expect(screen.getAllByText(/MAIN/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Active/).length).toBeGreaterThan(0);
    expect(screen.getByRole("navigation", { name: "Employee detail" })).toBeVisible();
    expect(screen.getByRole("region", { name: "Employee history" })).toHaveTextContent("ACP Employee Mobile role assigned");
    expect(screen.getByRole("region", { name: "Employee history" })).toHaveTextContent("ACP NATIVE");
    expect(
      screen.queryByText(/compensation|net pay|tax election/i),
    ).not.toBeInTheDocument();
  });

  it("certifies an exact persisted source target without name matching", async () => {
    mockEligibility();
    const bind = vi.fn();
    vi.mocked(workforceHooks.useRealRosterReadiness).mockReturnValue({
      query: {
        isLoading: false,
        isError: false,
        data: {
          total: 8,
          bound: 0,
          field_tech_total: 5,
          field_tech_capability_ready: 0,
          source_evidence_total: 1,
          source_only_total: 0,
          certification_required_total: 8,
          login_ready_total: 0,
          membership_ready_total: 0,
          branch_ready_total: 0,
          mobile_ready_total: 0,
          dispatch_ready_total: 0,
          timekeeping_ready_total: 0,
          payroll_identity_ready_total: 0,
          source_evidence: [{
            source_system: "HCP",
            source_employee_id: "pro_exact_source_1",
            source_disposition: "CREATE_ENTERPRISE_EMPLOYEE_CANDIDATE",
            source_branch_id: "branch-1",
            acp_employee_id: "employee-exact-target",
            roster_key: null,
            certification_state: "OWNER_CERTIFICATION_REQUIRED",
            evidence_version: 1,
            recorded_at: "2026-09-01T00:00:00Z",
          }],
          items: [{
            roster_key: "melvin-santiago",
            display_name: "Melvin Santiago",
            operating_role: "FIELD_TECH",
            field_tech: true,
            employee_id: null,
            employee_display_name: null,
            user_state: "AUTHENTICATED_VERIFICATION_REQUIRED",
            employee_state: "AUTHENTICATED_VERIFICATION_REQUIRED",
            membership_state: "AUTHENTICATED_VERIFICATION_REQUIRED",
            branch_state: "AUTHENTICATED_VERIFICATION_REQUIRED",
            role_state: "AUTHENTICATED_VERIFICATION_REQUIRED",
            workforce_profile_state: "AUTHENTICATED_VERIFICATION_REQUIRED",
            technician_capability_state: "AUTHENTICATED_VERIFICATION_REQUIRED",
            mobile_state: "AUTHENTICATED_VERIFICATION_REQUIRED",
            credential_state: "AUTHENTICATED_VERIFICATION_REQUIRED",
            availability_state: "AUTHENTICATED_VERIFICATION_REQUIRED",
            dispatch_state: "AUTHENTICATED_VERIFICATION_REQUIRED",
            timekeeping_state: "AUTHENTICATED_VERIFICATION_REQUIRED",
            payroll_linkage_state: "AUTHENTICATED_VERIFICATION_REQUIRED",
            blockers: ["OWNER_EMPLOYEE_BINDING_REQUIRED"],
          }],
        },
      },
      bind: { isPending: false, mutate: bind },
      prepareFieldReadiness: { isPending: false, mutate: vi.fn() },
      canBind: true,
    } as never);
    vi.mocked(workforceHooks.useWorkforceDirectory).mockReturnValue({ data: [] } as never);
    vi.mocked(workforceHooks.useWorkforceEmployee).mockReturnValue({ data: undefined } as never);
    render(<MemoryRouter><WorkforceRoute /></MemoryRouter>);

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Certify HCP pro_exact_source_1" }), "melvin-santiago");
    await userEvent.click(screen.getByRole("button", { name: "Confirm exact source target" }));

    expect(bind).toHaveBeenCalledWith({ rosterKey: "melvin-santiago", employeeId: "employee-exact-target" });
  });

  it("shows ordinary office identity, delivery, and access status", async () => {
    mockEligibility();
    vi.mocked(workforceHooks.useWorkforceDirectory).mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: [summary],
    } as never);
    vi.mocked(workforceHooks.useWorkforceEmployee).mockImplementation(
      (id) => ({
        isLoading: false,
        isError: false,
        data: id
          ? {
              ...summary,
              capabilities: [],
              certifications: [],
              languages: [],
              branches: [],
              work_restrictions: [],
              equipment_capabilities: [],
              availability: [],
            }
          : undefined,
      }) as never,
    );
    vi.mocked(workforceHooks.useEmployeeAdministration).mockImplementation(
      (id) => ({
        isLoading: false,
        isError: false,
        data: id
          ? {
              ...summary,
              membership_id: "membership-1",
              membership_status: "active",
              user_status: "active",
              authorization_version: 4,
              branch_ids: ["branch-1"],
              role_codes: ["ACP_EMPLOYEE_MOBILE", "OFFICE_MANAGER"],
              onboarding_status: "activated",
              invitation_status: "consumed",
              delivery_status: "accepted",
              login_email: "employee@example.test",
              masked_login: "e***@example.test",
              access_status: "ACTIVE",
              mobile_readiness: "READY",
              mobile_readiness_blockers: [],
              permissions: [],
              workforce: {
                ...summary,
                capabilities: [],
                certifications: [],
                languages: [],
                branches: [],
                work_restrictions: [],
                equipment_capabilities: [],
                availability: [],
              },
            }
          : undefined,
      }) as never,
    );
    render(
      <MemoryRouter>
        <WorkforceRoute />
      </MemoryRouter>,
    );
    await userEvent.click(screen.getByRole("button", { name: /Marisol Rivera/ }));
    expect(screen.getByText("employee@example.test")).toBeVisible();
    expect(screen.getByText("ACP EMPLOYEE MOBILE, OFFICE MANAGER")).toBeVisible();
    expect(screen.getAllByText("MAIN").length).toBeGreaterThan(0);
    expect(screen.getByText("consumed")).toBeVisible();
    expect(screen.getByText("Provider accepted")).toBeVisible();
    expect(screen.getByText("activated")).toBeVisible();
    expect(screen.getAllByText("READY")).not.toHaveLength(0);
  });

  it("filters by explicit capability evidence", async () => {
    mockEligibility();
    vi.mocked(workforceHooks.useWorkforceDirectory).mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: [summary],
    } as never);
    vi.mocked(workforceHooks.useWorkforceEmployee).mockReturnValue({
      isLoading: false,
      isError: false,
      data: undefined,
    } as never);
    render(
      <MemoryRouter>
        <WorkforceRoute />
      </MemoryRouter>,
    );
    await userEvent.type(
      screen.getByRole("textbox", { name: "Search workforce" }),
      "water_heater",
    );
    expect(screen.getByText("Marisol Rivera")).toBeInTheDocument();
  });
});
