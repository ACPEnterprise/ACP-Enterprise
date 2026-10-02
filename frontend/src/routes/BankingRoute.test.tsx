import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BankingRoute } from "./BankingRoute";
import * as banking from "../api/banking";

vi.mock("../auth", () => ({ useHasPermission: () => true }));
vi.mock("../api/banking", () => ({
  getBankingSummary: vi.fn(),
  getBankTransactions: vi.fn(),
  previewBankImport: vi.fn(),
  confirmBankImport: vi.fn(),
  getMatchReview: vi.fn(),
  matchBankTransaction: vi.fn(),
  getBankDrilldown: vi.fn(),
  previewReconciliation: vi.fn(),
  getReconciliationHistory: vi.fn(),
  getCashFlow: vi.fn(),
}));

const transaction = {
  id: "txn-1",
  bank_account_id: "bank-1",
  external_transaction_id: "ext-1",
  posted_date: "2026-09-15",
  effective_date: null,
  amount: "125.00",
  currency: "USD",
  direction: "inflow",
  kind: "customer_payment",
  description: "Customer deposit",
  memo: null,
  state: "unmatched",
  source_as_of: "2026-09-15T12:00:00Z",
};

function renderRoute() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <BankingRoute />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("BankingRoute", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(banking.getBankingSummary).mockResolvedValue([
      {
        account: {
          id: "bank-1",
          institution_name: "Example Bank",
          account_name: "Operating",
          account_type: "checking",
          masked_identity: "•••• 4321",
          currency: "USD",
          status: "active",
          source_system: "statement_import",
          source_as_of: "2026-09-30T12:00:00Z",
          opening_balance: "1000.00",
          opening_balance_date: "2026-09-01",
        },
        imported_count: 10,
        matched_count: 7,
        unmatched_count: 2,
        review_required_count: 1,
        transfer_candidate_count: 1,
        active_reconciliation_state: "in_progress",
        current_difference: "25.00",
        last_reconciled_through: "2026-08-31",
        latest_closed_reconciliation: null,
      },
    ]);
    vi.mocked(banking.getBankTransactions).mockResolvedValue([transaction]);
    vi.mocked(banking.getMatchReview).mockResolvedValue([
      {
        transaction,
        match_id: null,
        match_state: "ambiguous",
        target_type: "payment",
        target_identity: "payment-1",
        reason_code: "multiple_candidates",
        deterministic: false,
      },
    ]);
    vi.mocked(banking.getReconciliationHistory).mockResolvedValue([]);
    vi.mocked(banking.getCashFlow).mockResolvedValue({
      period_start: "2026-09-01",
      period_end: "2026-09-30",
      basis: "posted_cash_movement",
      cutoff: "2026-09-30T23:59:59Z",
      completeness: "PARTIAL",
      beginning_cash: "1000.00",
      operating_activities: { amount: "250.00", journal_ids: ["journal-1"] },
      investing_activities: { amount: "0.00", journal_ids: [] },
      financing_activities: { amount: "0.00", journal_ids: [] },
      unclassified_amount: "25.00",
      unclassified_journal_ids: ["journal-2"],
      net_change: "250.00",
      ending_cash: "1250.00",
      canonical_bank_cash: null,
      difference: null,
      tie_status: "UNAVAILABLE",
    });
  });

  it("presents a normal account summary and canonical review states", async () => {
    renderRoute();

    expect(await screen.findByRole("heading", { name: "Banking" })).toBeVisible();
    expect(screen.getByRole("combobox", { name: "Bank account" })).toHaveDisplayValue(
      "Example Bank · Operating •••• 4321",
    );
    expect(screen.getByText("25.00", { exact: false })).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Needs Review" }));
    expect(await screen.findByText("Ambiguous")).toBeVisible();
    expect(screen.getByText("Multiple candidates")).toBeVisible();
    expect(screen.queryByRole("button", { name: /ignore|reject/i })).not.toBeInTheDocument();
  });

  it("keeps close disabled even at zero until the backend supplies a preparer handoff", async () => {
    vi.mocked(banking.previewReconciliation).mockResolvedValue({
      bank_account_id: "bank-1",
      statement_identity: "September statement",
      period_start: "2026-09-01",
      period_end: "2026-09-30",
      beginning_balance: "1000.00",
      ending_balance: "1125.00",
      book_balance: "1125.00",
      cleared_total: "125.00",
      outstanding_total: "0.00",
      difference: "0.00",
      unresolved_exceptions: 0,
      can_close: true,
      blocker_reasons: [],
    });
    renderRoute();
    fireEvent.click(await screen.findByRole("button", { name: "Reconcile" }));
    fireEvent.change(screen.getByLabelText("Statement reference"), { target: { value: "September statement" } });
    fireEvent.change(screen.getByLabelText("Statement ending balance"), { target: { value: "1125.00" } });
    fireEvent.click(screen.getByRole("button", { name: "Calculate difference" }));

    expect((await screen.findAllByText("$0.00")).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Close reconciliation" })).toBeDisabled();
    expect(screen.getByText(/distinct preparer submits/i)).toBeVisible();
  });

  it("previews before confirming and preserves canonical item dispositions", async () => {
    vi.mocked(banking.previewBankImport).mockResolvedValue({
      bank_account_id: "bank-1",
      statement_identity: "September statement",
      period_start: "2026-09-01",
      period_end: "2026-09-30",
      opening_balance: "1000.00",
      ending_balance: "1125.00",
      transaction_count: 1,
      new_count: 1,
      replay_count: 0,
      duplicate_count: 0,
      conflict_count: 0,
      invalid_count: 0,
      preview_digest: "a".repeat(64),
      dispositions: [
        {
          source_system: "sanitized_statement",
          source_identity: "entry-1",
          disposition: "NEW",
          reason: "No prior evidence",
        },
      ],
      transactions: [],
    });
    vi.mocked(banking.confirmBankImport).mockResolvedValue({
      preview_digest: "a".repeat(64),
      persisted_count: 1,
      replay_count: 0,
      quarantined_count: 0,
      dispositions: [],
    });
    renderRoute();
    fireEvent.click(await screen.findByRole("button", { name: "Import" }));
    const statement = {
      statement_identity: "September statement",
      period_start: "2026-09-01",
      period_end: "2026-09-30",
      opening_balance: "1000.00",
      ending_balance: "1125.00",
      transactions: [],
    };
    const file = new File([JSON.stringify(statement)], "statement.json", { type: "application/json" });
    Object.defineProperty(file, "text", { value: async () => JSON.stringify(statement) });
    fireEvent.change(screen.getByLabelText("Statement file"), { target: { files: [file] } });

    expect(await screen.findByText(/September statement/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Preview import" }));
    expect(await screen.findByText(/No prior evidence/)).toBeVisible();
    expect(banking.confirmBankImport).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Confirm import" }));

    expect(await screen.findByText(/Imported 1/)).toBeVisible();
    expect(banking.confirmBankImport).toHaveBeenCalledWith(
      "bank-1",
      statement,
      "a".repeat(64),
    );
  });

  it("renders formal partial cash flow without turning missing authority into completeness", async () => {
    renderRoute();
    fireEvent.click(await screen.findByRole("button", { name: "Cash Flow" }));

    expect(await screen.findByText("Statement of Cash Flows")).toBeVisible();
    expect(await screen.findByText("Partial")).toBeVisible();
    expect(screen.getByText("$1,000.00")).toBeVisible();
    expect(screen.getByText("$1,250.00")).toBeVisible();
    expect(screen.getByText(/needs classification/i)).toHaveTextContent("$25.00");
    await waitFor(() => expect(banking.getCashFlow).toHaveBeenCalled());
  });
});
