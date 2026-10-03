import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { OpeningControlProjectionReview } from "./OpeningControlProjectionReview";
import type { OpeningControlDetail } from "../../api/accountingClose";

vi.mock("../../hooks/useAccountingClose", async () => {
  const actual = await vi.importActual<typeof import("../../hooks/useAccountingClose")>("../../hooks/useAccountingClose");
  return { ...actual, useOpeningSubledger: () => ({ isLoading: false, isError: false, data: { items: [], offset: 0, limit: 100, total: 0 } }) };
});

const detail = (overrides: Partial<OpeningControlDetail> = {}): OpeningControlDetail => ({
  package: {
    id: "opening-package-1", company_id: "company-1", realm_id: "realm-1", package_identity: "qbo-package-1",
    cutoff_at: "2026-09-30T23:59:59Z", status: "READY_FOR_REVIEW", evidence_digest: "digest",
    total_debits: "100.00", total_credits: "100.00", ar_control_balance: "25.00", ar_subledger_balance: "25.00",
    ap_control_balance: "10.00", ap_subledger_balance: "10.00", version: 1, approved_by_user_id: null, applied_journal_id: null,
  },
  trial_balance: [
    { source_identity: "cash", account_type: "Bank", equity_category: null, debit: "100.00", credit: "0.00", source_version: "1", source_digest: "digest" },
    { source_identity: "retained-earnings", account_type: "Equity", equity_category: "RETAINED_EARNINGS", debit: "0.00", credit: "100.00", source_version: "1", source_digest: "digest" },
  ],
  total_debits: "100.00", total_credits: "100.00", difference: "0.00", equity_categories: ["RETAINED_EARNINGS"],
  ar_difference: "0.00", ap_difference: "0.00", source_as_of: "2026-09-30T23:59:59Z", cutoff_at: "2026-09-30T23:59:59Z",
  lifecycle: [{ state: "SEALED", at: "2026-10-01T12:00:00Z", actor_role: "PREPARER", actor_display_name: "Accountant" }],
  ...overrides,
});

const renderReview = (value: OpeningControlDetail) => render(
  <QueryClientProvider client={new QueryClient()}>
    <OpeningControlProjectionReview value={value} />
  </QueryClientProvider>,
);

describe("OpeningControlProjectionReview", () => {
  it("renders a balanced server-owned package without calculating accounting values", () => {
    renderReview(detail());
    expect(screen.getByRole("heading", { name: "Opening Trial Balance" })).toBeVisible();
    expect(screen.getByText("cash")).toBeVisible();
    expect(screen.getAllByText("100.00").length).toBeGreaterThan(1);
  });

  it("keeps an unbalanced package visibly in review", () => {
    renderReview(detail({ difference: "1.00", total_debits: "101.00", package: { ...detail().package, status: "REVIEW_REQUIRED", total_debits: "101.00" } }));
    expect(screen.getByText(/unresolved balance/i)).toBeVisible();
    expect(screen.getByText("1.00")).toBeVisible();
  });

  it("renders server-provided lifecycle and preserves unavailable values", () => {
    renderReview(detail({ ar_difference: null, ap_difference: null }));
    expect(screen.getAllByText(/Accountant/).length).toBeGreaterThan(0);
    expect(screen.getByText(/AR control difference:/)).toBeVisible();
  });
});
