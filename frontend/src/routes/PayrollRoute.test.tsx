import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  useComplianceSchemas,
  usePayrollOperationsSummary,
  usePayrollReports,
} from "../hooks/usePayroll";
import { PayrollRoute } from "./PayrollRoute";

const permissionState = vi.hoisted(() => ({ values: new Set<string>() }));

vi.mock("../auth", () => ({
  useHasPermission: (code: string) => permissionState.values.has(code),
}));
vi.mock("../hooks/usePayroll", () => ({
  usePayrollOperationsSummary: vi.fn(),
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
    vi.mocked(useComplianceSchemas).mockReturnValue(query([]) as never);
  });

  it("disables every protected query without complete read authority", () => {
    render(<PayrollRoute />);
    expect(screen.getByText(/not authorized/i)).toBeVisible();
    expect(usePayrollOperationsSummary).toHaveBeenCalledWith(false);
    expect(usePayrollReports).toHaveBeenCalledWith(false);
    expect(useComplianceSchemas).toHaveBeenCalledWith(false);
  });

  it("enables readiness only with reporting and run read authority", () => {
    permissionState.values = new Set([
      "COMPANY_PAYROLL_REPORTING_READ",
      "COMPANY_PAYROLL_RUN_READ",
    ]);
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
  });
});
