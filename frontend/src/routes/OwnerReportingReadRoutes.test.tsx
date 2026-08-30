import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AccountsPayableRoute } from "./AccountsPayableRoute";
import { PayrollRoute } from "./PayrollRoute";

let permissions = new Set<string>();
const apMocks = vi.hoisted(() => ({
  aging: vi.fn(() => ({ isPending: false, isError: false, data: [] })),
  matchWorkbench: vi.fn((props: { canReview: boolean }) =>
    props.canReview ? "Review matching evidence" : "Read-only matching evidence"),
}));

vi.mock("../auth", () => ({
  useHasPermission: (code: string) => permissions.has(code),
}));
vi.mock("../hooks/usePayroll", () => ({
  usePayrollOperationsSummary: () => ({
    isPending: false,
    isError: false,
    data: {
      blocker_count: 0,
      history_ready: false,
      aggregate_approved_gross: "0.00",
      aggregate_approved_net: "0.00",
      reconciliation_state: "incomplete",
      provider_readiness: { filing: "not_configured", payment: "not_configured", remittance: "not_configured" },
      run_counts: {}, member_dispositions: {}, payment_counts: {}, remittance_counts: {}, reporting_counts: {}, statement_counts: {}, adjustment_counts: {},
    },
  }),
  usePayrollReports: () => ({ isPending: false, isError: false, data: [] }),
  useComplianceSchemas: () => ({ isPending: false, isError: false, data: [] }),
}));
vi.mock("../hooks/useAccountsPayable", () => ({
  useAPAging: apMocks.aging,
  useAPMutations: () => ({ createVendor: { mutateAsync: vi.fn(), isPending: false } }),
}));
vi.mock("../components/purchasing/ProcurementMatchWorkbench", () => ({
  ProcurementMatchWorkbench: apMocks.matchWorkbench,
}));

describe("owner reporting read routes", () => {
  beforeEach(() => { permissions = new Set(); vi.clearAllMocks(); });

  it("renders Payroll Administration with reporting-read alone", () => {
    permissions.add("COMPANY_PAYROLL_REPORTING_READ");
    render(<PayrollRoute />);
    expect(screen.getByRole("heading", { name: "Payroll Administration" })).toBeVisible();
  });

  it("renders Accounts Payable reporting with report-read alone", () => {
    permissions.add("COMPANY_ACCOUNTS_PAYABLE_REPORT_READ");
    render(<AccountsPayableRoute />);
    expect(screen.getByRole("heading", { name: "Accounts Payable" })).toBeVisible();
    expect(apMocks.aging).toHaveBeenCalledWith(expect.any(String), true);
    expect(apMocks.matchWorkbench).not.toHaveBeenCalled();
  });

  it("does not request AP reporting for operational-read alone", () => {
    permissions.add("COMPANY_ACCOUNTS_PAYABLE_READ");
    render(<AccountsPayableRoute />);
    expect(screen.getByRole("heading", { name: "Accounts Payable" })).toBeVisible();
    expect(apMocks.aging).toHaveBeenCalledWith(expect.any(String), false);
    expect(apMocks.matchWorkbench).toHaveBeenCalled();
    expect(apMocks.matchWorkbench.mock.calls[0]?.[0]).toEqual(
      expect.objectContaining({ canReview: false }),
    );
  });

  it("keeps both routes fail-closed without an accepted read permission", () => {
    const payroll = render(<PayrollRoute />);
    expect(screen.getByText(/not authorized to view Payroll/i)).toBeVisible();
    payroll.unmount();
    render(<AccountsPayableRoute />);
    expect(screen.getByText(/not authorized to view Accounts Payable/i)).toBeVisible();
  });
});
