import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { WorkforceRoute } from "./WorkforceRoute";

const approveMutation = vi.hoisted(() => vi.fn());

vi.mock("../auth", () => ({
  useAuth: () => ({
    activeCompany: { id: "company-1" },
    permissionCodes: [
      "COMPANY_TIMEKEEPING_ADMIN_READ",
      "COMPANY_TIMEKEEPING_APPROVE",
      "COMPANY_PAYROLL_REPORTING_READ",
    ],
  }),
}));
vi.mock("../features/administration/hooks", () => ({
  useRoles: () => ({ data: [] }),
}));
vi.mock("../hooks/useWorkforce", () => ({
  useSourceCertification: () => ({
    query: { data: undefined, isLoading: false, isError: false },
    decide: { mutate: vi.fn(), isPending: false },
  }),
  useRealRosterReadiness: () => ({
    query: { data: undefined, isLoading: false, isError: false },
    bind: { mutate: vi.fn(), isPending: false },
    prepareFieldReadiness: { mutate: vi.fn(), isPending: false },
    canBind: false,
  }),
  useWorkforceDirectory: () => ({ data: [], isLoading: false, isError: false }),
  useHistoricalWorkforceIdentities: () => ({ data: { items: [] }, isLoading: false, isError: false }),
  useWorkforceEmployee: () => ({
    data: undefined,
    isLoading: false,
    isError: false,
  }),
  useEmployeeFieldReadiness: () => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
  }),
  useEmployeeTimeline: () => ({
    data: undefined,
    isLoading: false,
    isError: false,
  }),
  useEmployeeAdministration: () => ({
    data: undefined,
    isLoading: false,
    isError: false,
  }),
  useEmployeePermissionUpdate: () => ({
    isPending: false,
    mutate: vi.fn(),
  }),
  useEmployeeFunctionalAccess: () => ({
    query: { data: [], isLoading: false, isError: false },
    grant: { mutate: vi.fn(), isPending: false, isError: false },
    revoke: { mutate: vi.fn(), isPending: false, isError: false },
  }),
  useEmployeeAccessLock: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
  useEmployeeAccessMutation: () => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
  }),
  useEmployeePasswordReset: () => ({
    query: { data: undefined },
    mutation: { mutate: vi.fn(), isPending: false, isError: false },
  }),
  useWorkforceEligibility: () => ({
    mutate: vi.fn(),
    data: undefined,
    isPending: false,
    isError: false,
  }),
}));
vi.mock("../hooks/useWorkdayTime", () => ({
  useAdminTimecardReview: () => ({
    data: {
      pay_period: { id: "period-1", period_start: "2026-09-06", period_end: "2026-09-12" },
      items: [{
        employee_id: "employee-approval",
        employee_number: "EMP-2",
        display_name: "Approval Employee",
        entry_count: 1,
        total_minutes: 480,
        exception_codes: [],
        entries: [{
          entry_id: "entry-approval",
          revision_id: "revision-submitted",
          revision_number: 2,
          work_date: "2026-09-07",
          timezone: "America/New_York",
          provenance: "employee_punch",
          start_at: "2026-09-07T13:00:00Z",
          end_at: "2026-09-07T21:00:00Z",
          approved_duration_minutes: 480,
          state: "submitted",
          supersedes_revision_id: null,
          correction_reason: null,
          correction_kind: null,
          reviewed_by_user_id: "employee-user",
          approved_at: null,
        }],
      }],
    },
    isLoading: false,
    isError: false,
  }),
  useTimeCorrection: () => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
  }),
  useApproveTimeEntry: () => ({
    mutate: approveMutation,
    isPending: false,
    isError: false,
  }),
  usePayPeriods: () => ({
    data: [
      { id: "period-1", period_start: "2026-09-06", period_end: "2026-09-12" },
    ],
    isLoading: false,
    isError: false,
  }),
  useAdminTimecardOperations: () => ({
    data: {
      pay_period: {
        id: "period-1",
        period_start: "2026-09-06",
        period_end: "2026-09-12",
      },
      employees: [
        {
          employee_id: "employee-1",
          employee_number: "EMP-1",
          display_name: "Sanctioned Employee",
          accepted_minutes: 60,
          total_supported_minutes: 60,
          active_open_clock: false,
          missing_clock_out: false,
          review_state: "ACCEPTED",
          days: [
            {
              work_date: "2026-09-06",
              total_supported_minutes: 480,
              accepted_minutes: 480,
              job_minutes: 480,
              non_job_supported_minutes: 0,
              unclassified_minutes: 0,
              has_overlap: false,
              has_correction: true,
              review_state: "ACCEPTED",
              intervals: [
                {
                  revision_id: "revision-2",
                  revision_number: 2,
                  start_at: "2026-09-06T13:00:00Z",
                  end_at: "2026-09-06T21:00:00Z",
                  job_number: "JOB-1001",
                  supported_minutes: 480,
                  corrected: true,
                  overlap: false,
                  provenance: "authorized_manual_entry",
                  review_state: "ACCEPTED",
                  audit_digest: "safe-digest",
                },
              ],
            },
          ],
        },
      ],
    },
    isLoading: false,
    isError: false,
  }),
}));

describe("Workforce timecard navigation", () => {
  it("opens the Employee requested by the Payroll register link", () => {
    render(
      <MemoryRouter
        initialEntries={[
          "/employees?employee=employee-1&period=period-1#timecard-operations",
        ]}
      >
        <WorkforceRoute />
      </MemoryRouter>,
    );
    const disclosure = screen
      .getByText("Sanctioned Employee")
      .closest("details");
    expect(disclosure).toHaveAttribute("open");
    expect(
      screen.getByRole("heading", { name: "Weekly totals" }),
    ).toBeVisible();
    expect(
      screen.getByText("8.00 supported · 8.00 accepted hours"),
    ).toBeVisible();
    expect(screen.getByText("Revision 2 · verified")).toBeVisible();
    expect(screen.queryByText("Pay period required")).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Review Payroll period" }),
    ).toHaveAttribute("href", "/payroll?period=period-1");
    expect(
      screen.getByRole("navigation", { name: "Team workspace" }),
    ).toBeVisible();
    expect(screen.getByRole("link", { name: "Employees" })).toHaveAttribute(
      "href",
      "#employee-roster",
    );
    expect(
      screen.getByRole("link", { name: "Time & Attendance" }),
    ).toHaveAttribute("href", "#timecard-operations");
  });

  it("requires explicit confirmation before approving a submitted revision", async () => {
    approveMutation.mockClear();
    render(<MemoryRouter initialEntries={["/employees?employee=employee-1&period=period-1#timecard-operations"]}><WorkforceRoute /></MemoryRouter>);
    await userEvent.click(screen.getByRole("button", { name: "Approve 2026-09-07" }));
    expect(screen.getByRole("dialog", { name: "Approve submitted time?" })).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Approve time" }));
    expect(approveMutation).toHaveBeenCalledWith("revision-submitted", expect.any(Object));
  });
});
