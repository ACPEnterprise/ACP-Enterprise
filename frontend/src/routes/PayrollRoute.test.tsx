import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  useComplianceSchemas,
  usePayrollOperationsSummary,
  usePayrollOperatingRegisters,
  usePayrollReports,
} from "../hooks/usePayroll";
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
  });

  it("disables every protected query without reporting read authority", () => {
    render(<PayrollRoute />);
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
    render(<PayrollRoute />);
    expect(screen.getByRole("heading", { name: "Payroll Administration" })).toBeVisible();
    expect(usePayrollOperationsSummary).toHaveBeenCalledWith(true);
    expect(usePayrollReports).toHaveBeenCalledWith(true);
    expect(useComplianceSchemas).toHaveBeenCalledWith(true);
    expect(usePayrollOperatingRegisters).toHaveBeenCalledWith(true);
  });

  it("shows exact blockers without implying filing or payment", () => {
    permissionState.values = new Set(["COMPANY_PAYROLL_REPORTING_READ"]);
    vi.mocked(usePayrollOperationsSummary).mockReturnValue(query({ blocker_count: 1, history_ready: false, aggregate_approved_gross: "0.00", aggregate_approved_net: "0.00", reconciliation_state: "attention_required", provider_readiness: { filing: "not_configured", payment: "not_configured", remittance: "not_configured" }, run_counts: { assembled: 1 }, member_dispositions: { blocked: 1 }, payment_counts: {}, remittance_counts: {}, reporting_counts: {}, statement_counts: {}, adjustment_counts: {} }) as never);
    vi.mocked(usePayrollOperatingRegisters).mockReturnValue(query([{ run_id: "run-1", period_start: "2026-09-01", period_end: "2026-09-07", lifecycle: "assembled", review_state: "not_started", currency: "USD", members: [{ employee_id: "employee-1", employee_number: "E-1", employee_name: "Synthetic Employee", status: "BLOCKED_FOR_PAYROLL", blockers: ["tax:federal_withholding_election:missing"], accepted_minutes: null, regular_minutes: null, overtime_minutes: null, gross: null, employee_taxes: null, deductions: null, net_pay: null, employer_liabilities: null }], liability_totals: { employee_taxes: "0.00", employee_deductions: "0.00", employer_liabilities: "0.00", net_pay: "0.00" } }]) as never);
    render(<PayrollRoute />);
    expect(screen.getByText(/tax · federal withholding election · missing/)).toBeVisible();
    expect(screen.getByText(/Manual filing\/payment required/)).toBeVisible();
  });
});
