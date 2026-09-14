import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  useComplianceSchemas,
  usePayrollOperationsSummary,
  usePayrollPeriodOperations,
  usePayrollOperatingRegisters,
  usePayrollReports,
} from "../hooks/usePayroll";
import { useCreatePayPeriod, useCurrentPayPeriod, usePayPeriods } from "../hooks/useWorkdayTime";
import { PayrollRoute } from "./PayrollRoute";

const permissionState = vi.hoisted(() => ({ values: new Set<string>() }));

vi.mock("../auth", () => ({
  useHasPermission: (code: string) => permissionState.values.has(code),
}));
vi.mock("../hooks/usePayroll", () => ({
  usePayrollOperationsSummary: vi.fn(),
  usePayrollOperatingRegisters: vi.fn(),
  usePayrollReports: vi.fn(),
  useComplianceSchemas: vi.fn(),
  usePayrollPeriodOperations: vi.fn(),
}));
vi.mock("../hooks/useWorkdayTime", () => ({
  useCreatePayPeriod: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useCurrentPayPeriod: vi.fn(() => ({
    data: undefined,
    isLoading: false,
    isError: false,
  })),
  usePayPeriods: vi.fn(() => ({ data: [], isLoading: false, isError: false })),
}));
vi.mock("../components/payroll/PayrollEmployeeSetup", () => ({
  PayrollEmployeeSetup: ({ employeeId }: { employeeId: string }) => (
    <div data-testid="payroll-employee-setup">Payroll setup for {employeeId}</div>
  ),
}));

const query = (data: unknown) => ({
  data,
  isPending: false,
  isError: false,
});

describe("PayrollRoute authorization", () => {
  beforeEach(() => {
    permissionState.values = new Set();
    vi.mocked(usePayrollOperationsSummary).mockReturnValue(
      query(undefined) as never,
    );
    vi.mocked(usePayrollReports).mockReturnValue(query([]) as never);
    vi.mocked(usePayrollOperatingRegisters).mockReturnValue(query([]) as never);
    vi.mocked(useComplianceSchemas).mockReturnValue(query([]) as never);
    vi.mocked(usePayrollPeriodOperations).mockReturnValue(
      query(undefined) as never,
    );
    vi.mocked(usePayPeriods).mockReturnValue(query([]) as never);
    vi.mocked(useCreatePayPeriod).mockReturnValue({ mutateAsync: vi.fn(), isPending: false } as never);
  });

  it("disables every protected query without reporting read authority", () => {
    render(
      <MemoryRouter>
        <PayrollRoute />
      </MemoryRouter>,
    );
    expect(screen.getByText(/not authorized/i)).toBeVisible();
    expect(usePayrollOperationsSummary).toHaveBeenCalledWith(false);
    expect(usePayrollReports).toHaveBeenCalledWith(false);
    expect(useComplianceSchemas).toHaveBeenCalledWith(false);
    expect(usePayrollOperatingRegisters).toHaveBeenCalledWith(false);
  });

  it("enables the safe reporting workspace with reporting read authority", () => {
    permissionState.values = new Set(["COMPANY_PAYROLL_REPORTING_READ"]);
    vi.mocked(usePayrollOperationsSummary).mockReturnValue(
      query({
        blocker_count: 0,
        history_ready: true,
        aggregate_approved_gross: "0.00",
        aggregate_approved_net: "0.00",
        reconciliation_state: "reconciled",
        provider_readiness: {
          filing: "not_configured",
          payment: "not_configured",
          remittance: "not_configured",
        },
        run_counts: {},
        member_dispositions: {},
        payment_counts: {},
        remittance_counts: {},
        reporting_counts: {},
        statement_counts: {},
        adjustment_counts: {},
      }) as never,
    );
    render(
      <MemoryRouter>
        <PayrollRoute />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("heading", { name: "Payroll Administration" }),
    ).toBeVisible();
    expect(usePayrollOperationsSummary).toHaveBeenCalledWith(true);
    expect(usePayrollReports).toHaveBeenCalledWith(true);
    expect(useComplianceSchemas).toHaveBeenCalledWith(true);
    expect(usePayrollOperatingRegisters).toHaveBeenCalledWith(true);
  });

  it("lets an authorized office operator create a pay period without UUID input", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({ id: "period-1" });
    permissionState.values = new Set([
      "COMPANY_PAYROLL_REPORTING_READ",
      "COMPANY_PAYROLL_POLICY_MANAGE",
    ]);
    vi.mocked(useCreatePayPeriod).mockReturnValue({ mutateAsync, isPending: false } as never);
    vi.mocked(usePayrollOperationsSummary).mockReturnValue(query({ blocker_count: 0, history_ready: false, aggregate_approved_gross: "0.00", aggregate_approved_net: "0.00", reconciliation_state: "attention_required", provider_readiness: { filing: "not_configured", payment: "not_configured", remittance: "not_configured" }, run_counts: {}, member_dispositions: {}, payment_counts: {}, remittance_counts: {}, reporting_counts: {}, statement_counts: {}, adjustment_counts: {} }) as never);
    render(<MemoryRouter><PayrollRoute /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText("Period start"), { target: { value: "2026-09-13" } });
    fireEvent.change(screen.getByLabelText("Period end"), { target: { value: "2026-09-19" } });
    fireEvent.change(screen.getByLabelText("Processing date"), { target: { value: "2026-09-21" } });
    fireEvent.change(screen.getByLabelText("Pay date"), { target: { value: "2026-09-25" } });
    fireEvent.click(screen.getByRole("button", { name: "Create Pay Period" }));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith(expect.objectContaining({ pay_frequency: "weekly" })));
    expect(screen.queryByLabelText(/company|uuid/i)).not.toBeInTheDocument();
  });

  it("shows exact blockers without implying filing or payment", () => {
    permissionState.values = new Set(["COMPANY_PAYROLL_REPORTING_READ"]);
    vi.mocked(usePayrollOperationsSummary).mockReturnValue(
      query({
        blocker_count: 1,
        history_ready: false,
        aggregate_approved_gross: "0.00",
        aggregate_approved_net: "0.00",
        reconciliation_state: "attention_required",
        provider_readiness: {
          filing: "not_configured",
          payment: "not_configured",
          remittance: "not_configured",
        },
        run_counts: { assembled: 1 },
        member_dispositions: { blocked: 1 },
        payment_counts: {},
        remittance_counts: {},
        reporting_counts: {},
        statement_counts: {},
        adjustment_counts: {},
      }) as never,
    );
    vi.mocked(usePayrollOperatingRegisters).mockReturnValue(
      query([
        {
          run_id: "run-1",
          period_start: "2026-09-01",
          period_end: "2026-09-07",
          lifecycle: "assembled",
          review_state: "not_started",
          currency: "USD",
          members: [
            {
              employee_id: "employee-1",
              employee_number: "E-1",
              employee_name: "Synthetic Employee",
              status: "BLOCKED_FOR_PAYROLL",
              blockers: ["tax:federal_withholding_election:missing"],
              accepted_minutes: null,
              regular_minutes: null,
              overtime_minutes: null,
              gross: null,
              employee_taxes: null,
              deductions: null,
              net_pay: null,
              employer_liabilities: null,
            },
          ],
          liability_totals: {
            employee_taxes: "0.00",
            employee_deductions: "0.00",
            employer_liabilities: "0.00",
            net_pay: "0.00",
          },
        },
      ]) as never,
    );
    render(
      <MemoryRouter>
        <PayrollRoute />
      </MemoryRouter>,
    );
    expect(
      screen.getByText(/tax · federal withholding election · missing/),
    ).toBeVisible();
    expect(
      screen.getByText(
        /Period liabilities unavailable until at least one Employee has an admitted calculation/i,
      ),
    ).toBeVisible();
    expect(screen.getByText(/Manual filing\/payment required/)).toBeVisible();
    expect(screen.queryByText("—")).not.toBeInTheDocument();
  });

  it("does not present aggregate zero when no approved Payroll run exists", () => {
    permissionState.values = new Set(["COMPANY_PAYROLL_REPORTING_READ"]);
    vi.mocked(usePayrollOperationsSummary).mockReturnValue(
      query({
        blocker_count: 0,
        history_ready: false,
        aggregate_approved_gross: "0.00",
        aggregate_approved_net: "0.00",
        reconciliation_state: "reconciled_or_no_activity",
        provider_readiness: {
          filing: "not_configured",
          payment: "not_configured",
          remittance: "not_configured",
        },
        run_counts: {},
        member_dispositions: {},
        payment_counts: {},
        remittance_counts: {},
        reporting_counts: {},
        statement_counts: {},
        adjustment_counts: {},
      }) as never,
    );
    render(
      <MemoryRouter>
        <PayrollRoute />
      </MemoryRouter>,
    );
    expect(screen.getAllByText("Unavailable")).toHaveLength(2);
    expect(screen.queryByText("0.00")).not.toBeInTheDocument();
  });

  it("shows truthful Employee period readiness without inventing candidates", () => {
    permissionState.values = new Set([
      "COMPANY_PAYROLL_REPORTING_READ",
      "COMPANY_TIMEKEEPING_ADMIN_READ",
    ]);
    vi.mocked(usePayrollOperationsSummary).mockReturnValue(
      query({
        blocker_count: 0,
        history_ready: false,
        aggregate_approved_gross: "0.00",
        aggregate_approved_net: "0.00",
        reconciliation_state: "attention_required",
        provider_readiness: {
          filing: "not_configured",
          payment: "not_configured",
          remittance: "not_configured",
        },
        run_counts: {},
        member_dispositions: {},
        payment_counts: {},
        remittance_counts: {},
        reporting_counts: {},
        statement_counts: {},
        adjustment_counts: {},
      }) as never,
    );
    vi.mocked(useCurrentPayPeriod).mockReturnValue(
      query({ id: "period-1" }) as never,
    );
    vi.mocked(usePayrollPeriodOperations).mockReturnValue(
      query({
        period_start: "2026-09-06",
        period_end: "2026-09-12",
        policy_readiness: "MISSING_CONFIGURATION",
        employees: [
          {
            employee_id: "employee-1",
            employee_number: "EMP-1",
            display_name: "Marisol Rivera",
            accepted_minutes: 2400,
            regular_candidate_minutes: null,
            overtime_candidate_minutes: null,
            compensation_readiness: "MISSING_CONFIGURATION",
            withholding_readiness: "MISSING_CONFIGURATION_OR_CALCULATION",
            gross_pay_readiness: "NOT_CALCULATED",
            payroll_review_status: "NOT_STARTED",
            exception_codes: ["GROSS_PAY_NOT_CALCULATED"],
          },
        ],
      }) as never,
    );
    render(
      <MemoryRouter initialEntries={["/payroll?employee=employee-1#payroll-employee-employee-1"]}>
        <PayrollRoute />
      </MemoryRouter>,
    );
    expect(screen.getByText("Marisol Rivera")).toBeVisible();
    expect(screen.getAllByText("Not calculated")).toHaveLength(2);
    expect(
      screen.getAllByText(/Missing configuration/i).length,
    ).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "View timecard" })).toHaveAttribute(
      "href",
      "/employees?employee=employee-1#timecard-employee-1",
    );
    expect(screen.getByText("Marisol Rivera").closest("tr")).toHaveAttribute(
      "id",
      "payroll-employee-employee-1",
    );
    expect(screen.getByText("Marisol Rivera").closest("tr")).toHaveClass(
      "bg-action-primary/5",
    );
    expect(screen.getByTestId("payroll-employee-setup")).toHaveTextContent(
      "Payroll setup for employee-1",
    );
  });
});
