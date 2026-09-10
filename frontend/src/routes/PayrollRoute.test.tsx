import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  useComplianceSchemas,
  usePayrollOperationsSummary,
  usePayrollPeriodOperations,
  usePayrollReports,
} from "../hooks/usePayroll";
import { useCurrentPayPeriod, usePayPeriods } from "../hooks/useWorkdayTime";
import { PayrollRoute } from "./PayrollRoute";

const permissionState = vi.hoisted(() => ({ values: new Set<string>() }));

vi.mock("../auth", () => ({
  useHasPermission: (code: string) => permissionState.values.has(code),
}));
vi.mock("../hooks/usePayroll", () => ({
  usePayrollOperationsSummary: vi.fn(),
  usePayrollReports: vi.fn(),
  useComplianceSchemas: vi.fn(),
  usePayrollPeriodOperations: vi.fn(),
}));
vi.mock("../hooks/useWorkdayTime", () => ({
  useCurrentPayPeriod: vi.fn(() => ({
    data: undefined,
    isLoading: false,
    isError: false,
  })),
  usePayPeriods: vi.fn(() => ({ data: [], isLoading: false, isError: false })),
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
    vi.mocked(useComplianceSchemas).mockReturnValue(query([]) as never);
    vi.mocked(usePayrollPeriodOperations).mockReturnValue(query(undefined) as never);
    vi.mocked(usePayPeriods).mockReturnValue(query([]) as never);
  });

  it("disables every protected query without reporting read authority", () => {
    render(<MemoryRouter><PayrollRoute /></MemoryRouter>);
    expect(screen.getByText(/not authorized/i)).toBeVisible();
    expect(usePayrollOperationsSummary).toHaveBeenCalledWith(false);
    expect(usePayrollReports).toHaveBeenCalledWith(false);
    expect(useComplianceSchemas).toHaveBeenCalledWith(false);
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
    render(<MemoryRouter><PayrollRoute /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Payroll Administration" })).toBeVisible();
    expect(usePayrollOperationsSummary).toHaveBeenCalledWith(true);
    expect(usePayrollReports).toHaveBeenCalledWith(true);
    expect(useComplianceSchemas).toHaveBeenCalledWith(true);
  });

  it("shows truthful Employee period readiness without inventing candidates", () => {
    permissionState.values = new Set([
      "COMPANY_PAYROLL_REPORTING_READ",
      "COMPANY_TIMEKEEPING_ADMIN_READ",
    ]);
    vi.mocked(usePayrollOperationsSummary).mockReturnValue(query({
      blocker_count: 0, history_ready: false, aggregate_approved_gross: "0.00",
      aggregate_approved_net: "0.00", reconciliation_state: "attention_required",
      provider_readiness: { filing: "not_configured", payment: "not_configured", remittance: "not_configured" },
      run_counts: {}, member_dispositions: {}, payment_counts: {}, remittance_counts: {},
      reporting_counts: {}, statement_counts: {}, adjustment_counts: {},
    }) as never);
    vi.mocked(useCurrentPayPeriod).mockReturnValue(query({ id: "period-1" }) as never);
    vi.mocked(usePayrollPeriodOperations).mockReturnValue(query({
      period_start: "2026-09-06", period_end: "2026-09-12", policy_readiness: "MISSING_CONFIGURATION",
      employees: [{ employee_id: "employee-1", employee_number: "EMP-1", display_name: "Marisol Rivera", accepted_minutes: 2400, regular_candidate_minutes: null, overtime_candidate_minutes: null, compensation_readiness: "MISSING_CONFIGURATION", withholding_readiness: "MISSING_CONFIGURATION_OR_CALCULATION", gross_pay_readiness: "NOT_CALCULATED", payroll_review_status: "NOT_STARTED", exception_codes: ["GROSS_PAY_NOT_CALCULATED"] }],
    }) as never);
    render(<MemoryRouter><PayrollRoute /></MemoryRouter>);
    expect(screen.getByText("Marisol Rivera")).toBeVisible();
    expect(screen.getAllByText("Not calculated")).toHaveLength(2);
    expect(screen.getAllByText(/Missing configuration/i).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "View timecard" })).toHaveAttribute("href", "/workforce?employee=employee-1#timecard-operations");
  });
});
