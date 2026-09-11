import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useQboAccountingEvidence } from "../../hooks/useQboAccountingEvidence";
import { QboSourceEvidence } from "./QboSourceEvidence";

vi.mock("../../hooks/useQboAccountingEvidence", () => ({
  useQboAccountingEvidence: vi.fn(),
}));

const unavailable = {
  amount: null,
  currency: null,
  state: "unavailable" as const,
};
const value = {
  contract_version: "qbo-accounting-evidence/v1",
  source: "quickbooks_online" as const,
  source_company_label: "Sanctioned company",
  source_company_id_masked: "***1234",
  accounting_basis: "cash" as const,
  as_of: "2026-09-10T12:00:00Z",
  acquired_at: "2026-09-10T12:05:00Z",
  refresh_state: "stale" as const,
  snapshot_id: "snapshot-1",
  snapshot_digest: "a".repeat(64),
  is_live: false as const,
  limitations: ["HCP reconciliation remains separate."],
  accounts: [
    {
      source_id: "1",
      name: "Checking",
      account_type: "Bank",
      account_subtype: null,
      balance: unavailable,
    },
  ],
  invoices: [],
  ar: { total_open: unavailable, current: unavailable, overdue: unavailable },
  payments: [],
  reports: [
    {
      report_key: "balance-sheet",
      label: "Balance Sheet",
      basis: "cash" as const,
      as_of: "2026-09-10T12:00:00Z",
      state: "available" as const,
      limitation: null,
    },
  ],
  mutation_authority: "none" as const,
};

describe("QboSourceEvidence", () => {
  it("labels snapshot/source truth and never renders a missing amount as zero", () => {
    vi.mocked(useQboAccountingEvidence).mockReturnValue({
      isPending: false,
      isError: false,
      data: value,
    } as unknown as ReturnType<typeof useQboAccountingEvidence>);
    render(<QboSourceEvidence enabled />);
    expect(
      screen.getByText(/sealed snapshot, not live synchronization/i),
    ).toBeVisible();
    expect(
      screen.getByText(/not posted ACP General Ledger truth/i),
    ).toBeVisible();
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);
    expect(screen.queryByText("$0.00")).not.toBeInTheDocument();
    expect(
      screen.getByText(/HCP reconciliation remains separate/i),
    ).toBeVisible();
  });

  it("keeps cash and accrual requests explicit", () => {
    vi.mocked(useQboAccountingEvidence).mockReturnValue({
      isPending: true,
    } as unknown as ReturnType<typeof useQboAccountingEvidence>);
    render(<QboSourceEvidence enabled />);
    fireEvent.change(screen.getByLabelText("QBO report basis"), {
      target: { value: "accrual" },
    });
    expect(useQboAccountingEvidence).toHaveBeenLastCalledWith("accrual", true);
  });
});
