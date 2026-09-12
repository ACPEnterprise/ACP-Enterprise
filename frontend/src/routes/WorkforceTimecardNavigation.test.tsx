import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { WorkforceRoute } from "./WorkforceRoute";

vi.mock("../auth", () => ({
  useAuth: () => ({
    activeCompany: { id: "company-1" },
    permissionCodes: ["COMPANY_TIMEKEEPING_ADMIN_READ"],
  }),
}));
vi.mock("../features/administration/hooks", () => ({
  useRoles: () => ({ data: [] }),
}));
vi.mock("../hooks/useWorkforce", () => ({
  useWorkforceDirectory: () => ({ data: [], isLoading: false, isError: false }),
  useWorkforceEmployee: () => ({
    data: undefined,
    isLoading: false,
    isError: false,
  }),
  useEmployeeAdministration: () => ({
    data: undefined,
    isLoading: false,
    isError: false,
  }),
  useEmployeeAccessMutation: () => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
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
      pay_period: {
        id: "period-1",
        period_start: "2026-09-06",
        period_end: "2026-09-12",
      },
      items: [],
    },
    isLoading: false,
    isError: false,
  }),
  useTimeCorrection: () => ({
    mutate: vi.fn(),
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
        initialEntries={["/employees?employee=employee-1#timecard-operations"]}
      >
        <WorkforceRoute />
      </MemoryRouter>,
    );
    const disclosure = screen
      .getByText("Sanctioned Employee")
      .closest("details");
    expect(disclosure).toHaveAttribute("open");
    expect(screen.getByRole("heading", { name: "Weekly totals" })).toBeVisible();
    expect(screen.getByText("8.00 supported · 8.00 accepted hours")).toBeVisible();
    expect(screen.getByText("Revision 2 · verified")).toBeVisible();
    expect(screen.getByRole("navigation", { name: "Team workspace" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Employees" })).toHaveAttribute("href", "#employee-roster");
    expect(screen.getByRole("link", { name: "Time & Attendance" })).toHaveAttribute("href", "#timecard-operations");
  });
});
