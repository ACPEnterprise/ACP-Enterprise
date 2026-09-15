import { fireEvent, render, screen, within } from "@testing-library/react";
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
  mode: "historical" as const,
  provider_environment: "historical_control" as const,
  company_identity_sha256: "c".repeat(64),
  company_info_verified_at: "2026-09-10T11:59:00Z",
  source_manifest_sha256: "d".repeat(64),
  completeness: "partial" as const,
  accounting_basis: "cash" as const,
  as_of: "2026-09-10T12:00:00Z",
  acquired_at: "2026-09-10T12:05:00Z",
  refresh_state: "stale" as const,
  snapshot_id: "snapshot-1",
  snapshot_digest: "a".repeat(64),
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
  invoices: [
    {
      source_id: "invoice-may-1",
      document_number: "1050",
      customer_label: "Source customer",
      transaction_date: "2026-05-14",
      due_date: "2026-06-14",
      source_status: "Open",
      total: { amount: "425.00", currency: "USD", state: "available" as const },
      open_balance: {
        amount: "125.00",
        currency: "USD",
        state: "available" as const,
      },
    },
    {
      source_id: "invoice-june-1",
      document_number: "1051",
      customer_label: "Later customer",
      transaction_date: "2026-06-01",
      due_date: "2026-07-01",
      source_status: "Open",
      total: { amount: "999.00", currency: "USD", state: "available" as const },
      open_balance: {
        amount: "999.00",
        currency: "USD",
        state: "available" as const,
      },
    },
  ],
  bills: [],
  ar: { total_open: unavailable, current: unavailable, overdue: unavailable },
  payments: [],
  conflicts: [
    {
      conflict_id: "conflict-1",
      subject_label: "Invoice 100",
      fact_name: "open balance",
      state: "conflicting" as const,
      source_assertions: [
        { source: "qbo" as const, value: "125.00", source_date: "2026-09-10" },
        { source: "hcp" as const, value: "0.00", source_date: "2026-09-09" },
      ],
      limitation: "No winner selected.",
    },
  ],
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
    expect(
      screen.getByText(/QBO, HCP, and ACP assertions remain separate/i),
    ).toBeVisible();
    expect(screen.getByText(/No winner selected/i)).toBeVisible();
    expect(screen.getByText(/Bill\/AP evidence is unavailable/i)).toBeVisible();
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

  it("generates a bounded historical source report without inferred zeros", () => {
    vi.mocked(useQboAccountingEvidence).mockReturnValue({
      isPending: false,
      isError: false,
      data: value,
    } as unknown as ReturnType<typeof useQboAccountingEvidence>);
    render(<QboSourceEvidence enabled />);
    expect(
      screen.getByText("QUICKBOOKS SOURCE EVIDENCE", { selector: "dd" }),
    ).toBeVisible();
    expect(screen.getByText("2026-05-01 through 2026-05-31")).toBeVisible();
    const activity = screen
      .getByRole("heading", { name: "Historical source activity report" })
      .closest("article");
    expect(activity).not.toBeNull();
    expect(within(activity!).getByText("$425.00")).toBeVisible();
    expect(within(activity!).queryByText("$999.00")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("QuickBooks report start date"), {
      target: { value: "2026-04-01" },
    });
    fireEvent.change(screen.getByLabelText("QuickBooks report end date"), {
      target: { value: "2026-04-30" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Generate" }));
    expect(screen.getByText(/No zero value was inferred/i)).toBeVisible();
  });
});
