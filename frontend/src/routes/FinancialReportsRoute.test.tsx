import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useFinancialReport } from "../hooks/useFinancialReporting";
import { FinancialReportsRoute } from "./FinancialReportsRoute";

let allowed = false;
vi.mock("../auth", () => ({ useHasPermission: () => allowed }));
vi.mock("../hooks/useFinancialReporting", () => ({
  useFinancialReport: vi.fn(() => ({
    isPending: false,
    isError: false,
    data: {
      scope: { scope_label: "Company", branch_id: null, includes_company_unassigned: true },
      manifest: { report_name: "trial_balance", definition_version: "acc-rpt-1.0", currency: "USD", accounting_basis: "accrual", ledger_cutoff: "a".repeat(64), checksum: "b".repeat(64) },
      quality: { integrity: "passed", completeness: "complete", freshness: "current", reconciliation: "reconciled", review: "unreviewed" },
      rows: [], total_beginning_balance: "0", total_debits: "0", total_credits: "0", total_ending_balance: "0",
    },
  })),
}));

describe("FinancialReportsRoute", () => {
  beforeEach(() => { allowed = false; });

  it("fails closed without report-read permission", () => {
    render(<FinancialReportsRoute />);
    expect(screen.getByText(/not authorized to read financial statements/i)).toBeVisible();
    expect(useFinancialReport).toHaveBeenCalledWith(expect.any(Object), false);
  });

  it("shows scope, cutoff, and independent quality states", () => {
    allowed = true;
    render(<FinancialReportsRoute />);
    expect(useFinancialReport).toHaveBeenCalledWith(expect.any(Object), true);
    expect(screen.getByText(/Company · USD · accrual · cutoff/)).toBeVisible();
    expect(screen.getByText("Integrity: passed")).toBeVisible();
    expect(screen.getByText("Reconciliation: reconciled")).toBeVisible();
    expect(screen.getByText(/Definition acc-rpt-1.0/)).toBeVisible();
  });
});
