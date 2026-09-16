import { fireEvent, render, screen } from "@testing-library/react";
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
      rows: [],
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
