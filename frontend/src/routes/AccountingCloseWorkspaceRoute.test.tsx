import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AccountingCloseWorkspaceRoute } from "./AccountingCloseWorkspaceRoute";
import * as closeHooks from "../hooks/useAccountingClose";
import * as evidenceHooks from "../hooks/useQboAccountingEvidence";
import * as applicationHooks from "../hooks/useQboNativeApplication";
import * as payrollHooks from "../hooks/usePayroll";

let permissions = new Set([
  "COMPANY_ACCOUNTING_REPORT_READ",
  "COMPANY_ACCOUNTING_RECONCILE",
  "COMPANY_ACCOUNTING_PERIOD_MANAGE",
  "COMPANY_ACCOUNTING_FINANCE_APPROVE",
]);
vi.mock("../auth", () => ({
  useHasPermission: (permission: string) => permissions.has(permission),
}));
vi.mock("../hooks/useAccountingClose");
vi.mock("../hooks/useQboAccountingEvidence");
vi.mock("../hooks/useQboNativeApplication");
vi.mock("../hooks/usePayroll");

describe("AccountingCloseWorkspaceRoute", () => {
  beforeEach(() => {
    permissions = new Set([
      "COMPANY_ACCOUNTING_REPORT_READ",
      "COMPANY_ACCOUNTING_RECONCILE",
      "COMPANY_ACCOUNTING_PERIOD_MANAGE",
      "COMPANY_ACCOUNTING_FINANCE_APPROVE",
    ]);
    vi.mocked(closeHooks.useAccountingPeriods).mockReturnValue({
      data: [
        {
          id: "period-1",
          company_id: "company-1",
          name: "September 2026",
          start_date: "2026-09-01",
          end_date: "2026-09-30",
          status: "closing",
          version: 2,
        },
      ],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof closeHooks.useAccountingPeriods>);
    vi.mocked(evidenceHooks.useQboAccountingEvidence).mockReturnValue({
      data: {
        as_of: "2026-09-30T23:59:59Z",
        accounting_basis: "accrual",
        reports: [
          {
            report_key: "pnl",
            label: "Profit and Loss",
            basis: "accrual",
            as_of: "2026-09-30",
            state: "available",
            limitation: null,
          },
        ],
      },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof evidenceHooks.useQboAccountingEvidence>);
    vi.mocked(applicationHooks.useQboReviewQueue).mockReturnValue({
      data: [
        {
          id: "review-1",
          source_family: "invoice",
          reference_number: "INV-101",
          exact_conflict: "Source and native amounts differ.",
          allowed_actions: [
            { action: "HOLD_FOR_ACCOUNTANT", required_authority: "ACCOUNTANT" },
          ],
          state: "OPEN",
        },
      ],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof applicationHooks.useQboReviewQueue>);
    vi.mocked(applicationHooks.useQboApplicationLedger).mockReturnValue({
      data: { source_evidence: { source_run_id: null } },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof applicationHooks.useQboApplicationLedger>);
    vi.mocked(closeHooks.useOpeningControlDetail).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof closeHooks.useOpeningControlDetail>);
    vi.mocked(closeHooks.usePayrollAccountingControl).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof closeHooks.usePayrollAccountingControl>);
    vi.mocked(payrollHooks.usePayrollOperatingRegisters).mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof payrollHooks.usePayrollOperatingRegisters>);
  });

  const renderRoute = () =>
    render(
      <MemoryRouter>
        <AccountingCloseWorkspaceRoute />
      </MemoryRouter>,
    );

  it("shows report availability without fabricating parity differences", () => {
    renderRoute();
    expect(
      screen.getByRole("heading", { name: "Accountant close workspace" }),
    ).toBeVisible();
    expect(screen.getByText("Income Statement / P&L")).toBeVisible();
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(1);
    expect(
      screen.getByText(/no browser-calculated parity is asserted/i),
    ).toBeVisible();
  });

  it("unifies canonical review items and normal workspace handoffs", () => {
    renderRoute();
    expect(screen.getByText("Source and native amounts differ.")).toBeVisible();
    expect(
      screen.getByRole("link", { name: /Opening, A\/R and A\/P/i }),
    ).toHaveAttribute("href", "/accounting/quickbooks-cutover");
    expect(screen.getByRole("link", { name: /^Payroll/i })).toHaveAttribute(
      "href",
      "/payroll",
    );
  });

  it("shows period status but withholds close when blocker evidence is not projected", () => {
    renderRoute();
    expect(screen.getByText("September 2026")).toBeVisible();
    expect(
      screen.getByText(
        /canonical blocker and reconciliation-evidence projection/i,
      ),
    ).toBeVisible();
    expect(
      screen.queryByRole("button", { name: /close period/i }),
    ).not.toBeInTheDocument();
  });

  it("fails closed for unauthorized users", () => {
    permissions = new Set();
    renderRoute();
    expect(
      screen.getByText(/Accounting report permission is required/i),
    ).toBeVisible();
  });
});
