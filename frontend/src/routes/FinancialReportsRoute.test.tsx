import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useFinancialReport } from "../hooks/useFinancialReporting";
import { FinancialReportsRoute } from "./FinancialReportsRoute";

let allowed = false;
let reportRows: Array<Record<string, string>> = [];
vi.mock("../auth", () => ({
  useHasPermission: () => allowed,
  useAuth: () => ({
    activeCompany: {
      branches: [{ id: "branch-1", name: "Main Branch", code: "MAIN" }],
    },
  }),
}));
vi.mock("../hooks/useFinancialReporting", () => ({
  useFinancialReport: vi.fn(() => ({
    isPending: false,
    isError: false,
    data: {
      scope: {
        scope_label: "Company",
        branch_id: null,
        includes_company_unassigned: true,
      },
      manifest: {
        report_name: "trial_balance",
        definition_version: "acc-rpt-1.0",
        currency: "USD",
        accounting_basis: "accrual",
        ledger_cutoff: "a".repeat(64),
        checksum: "b".repeat(64),
      },
      quality: {
        integrity: "passed",
        completeness: "complete",
        freshness: "current",
        reconciliation: "reconciled",
        review: "unreviewed",
      },
      rows: reportRows,
      total_beginning_balance: "0",
      total_debits: "0",
      total_credits: "0",
      total_ending_balance: "0",
    },
  })),
}));
vi.mock("../hooks/useQboAccountingEvidence", () => ({
  useQboAccountingEvidence: vi.fn(() => ({
    isPending: false,
    isError: true,
    data: undefined,
    refetch: vi.fn(),
  })),
  useQboSourceBackedProfitAndLoss: vi.fn(() => ({
    isPending: false,
    isError: true,
    data: undefined,
    refetch: vi.fn(),
  })),
}));

describe("FinancialReportsRoute", () => {
  beforeEach(() => {
    allowed = false;
    reportRows = [{
      account_id: "account-1", code: "1100", name: "Accounts Receivable",
      classification: "asset", beginning_balance: "125.5", debits: "20",
      credits: "5", ending_balance: "140.5", display_balance: "140.5",
    }];
  });

  it("fails closed without report-read permission", () => {
    render(<FinancialReportsRoute />);
    expect(
      screen.getByText(/not authorized to read financial statements/i),
    ).toBeVisible();
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
    expect(
      screen.getByRole("heading", { name: "QuickBooks source evidence" }),
    ).toBeVisible();
    expect(
      screen.getByText(/did not infer zeros or substitute native\/HCP data/i),
    ).toBeVisible();
    expect(screen.getByRole("option", { name: "Main Branch (MAIN)" })).toBeVisible();
    expect(screen.queryByLabelText(/Branch ID/i)).not.toBeInTheDocument();
    expect(screen.getByText("$125.50")).toBeVisible();
    expect(screen.getByText("$140.50")).toBeVisible();
  });

  it("rejects reversed report periods before changing the authoritative request", () => {
    allowed = true;
    render(<FinancialReportsRoute />);
    const requestBefore = vi.mocked(useFinancialReport).mock.calls.at(-1)?.[0];
    fireEvent.change(screen.getByLabelText("Start date"), {
      target: { value: "2026-09-20" },
    });
    fireEvent.change(screen.getByLabelText("End date"), {
      target: { value: "2026-09-10" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Generate" }));
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Choose a start date on or before the end date",
    );
    expect(vi.mocked(useFinancialReport).mock.calls.at(-1)?.[0]).toEqual(requestBefore);
  });

  it("explains an empty native report without implying a loading failure", () => {
    allowed = true;
    reportRows = [];
    render(<FinancialReportsRoute />);
    expect(screen.getByText(/No posted account balances exist for this report scope/i)).toBeVisible();
  });

  it("rejects reversed report periods before changing the authoritative request", () => {
    allowed = true;
    render(<FinancialReportsRoute />);
    const requestBefore = vi.mocked(useFinancialReport).mock.calls.at(-1)?.[0];
    fireEvent.change(screen.getByLabelText("Start date"), {
      target: { value: "2026-09-20" },
    });
    fireEvent.change(screen.getByLabelText("End date"), {
      target: { value: "2026-09-10" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Generate" }));
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Choose a start date on or before the end date",
    );
    expect(vi.mocked(useFinancialReport).mock.calls.at(-1)?.[0]).toEqual(requestBefore);
  });

  it("rejects reversed report periods before changing the authoritative request", () => {
    allowed = true;
    render(<FinancialReportsRoute />);
    const requestBefore = vi.mocked(useFinancialReport).mock.calls.at(-1)?.[0];
    fireEvent.change(screen.getByLabelText("Start date"), {
      target: { value: "2026-09-20" },
    });
    fireEvent.change(screen.getByLabelText("End date"), {
      target: { value: "2026-09-10" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Generate" }));
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Choose a start date on or before the end date",
    );
    expect(vi.mocked(useFinancialReport).mock.calls.at(-1)?.[0]).toEqual(requestBefore);
  });
});
