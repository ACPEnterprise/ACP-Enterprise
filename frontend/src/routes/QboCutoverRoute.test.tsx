import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { QboCutoverRoute } from "./QboCutoverRoute";
import * as evidenceHooks from "../hooks/useQboAccountingEvidence";
import * as applicationHooks from "../hooks/useQboNativeApplication";

let permissions = new Set([
  "COMPANY_ACCOUNTING_REPORT_READ",
  "COMPANY_ACCOUNTING_RECONCILE",
]);
vi.mock("../auth", () => ({
  useHasPermission: (permission: string) => permissions.has(permission),
}));
vi.mock("../hooks/useQboAccountingEvidence");
vi.mock("../hooks/useQboNativeApplication");

const amount = (value: string) => ({
  amount: value,
  currency: "USD",
  state: "available" as const,
});
const source = {
  contract_version: "qbo-accounting-evidence/v1",
  source: "quickbooks_online" as const,
  mode: "historical" as const,
  provider_environment: "historical_control" as const,
  company_identity_sha256: "c".repeat(64),
  company_info_verified_at: "2026-09-30T12:00:00Z",
  source_manifest_sha256: "m".repeat(64),
  completeness: "partial" as const,
  accounting_basis: "accrual" as const,
  as_of: "2026-09-30T23:59:59Z",
  acquired_at: "2026-10-01T12:00:00Z",
  refresh_state: "available" as const,
  snapshot_id: "snapshot-1",
  snapshot_digest: "d".repeat(64),
  limitations: ["opening_control_not_admitted"],
  accounts: [
    {
      source_id: "account-1",
      name: "Accounts Receivable",
      account_type: "Accounts Receivable",
      account_subtype: null,
      balance: amount("500.00"),
    },
  ],
  invoices: [
    {
      source_id: "invoice-1",
      document_number: "INV-101",
      customer_label: "Sanitized Customer",
      transaction_date: "2026-09-01",
      due_date: "2026-09-30",
      source_status: "Open",
      total: amount("600.00"),
      open_balance: amount("500.00"),
    },
  ],
  bills: [
    {
      source_id: "bill-1",
      document_number: "BILL-22",
      vendor_label: "Sanitized Vendor",
      transaction_date: "2026-09-03",
      due_date: "2026-10-03",
      source_status: "Open",
      total: amount("300.00"),
      open_balance: amount("250.00"),
    },
  ],
  ar: {
    total_open: amount("500.00"),
    invoice_evidence_count: 1,
    open_invoice_count: 1,
    closed_invoice_count: 0,
    current: amount("500.00"),
    overdue: amount("0.00"),
  },
  payments: [],
  reports: [],
  conflicts: [],
  mutation_authority: "none" as const,
};

describe("QboCutoverRoute", () => {
  beforeEach(() => {
    permissions = new Set([
      "COMPANY_ACCOUNTING_REPORT_READ",
      "COMPANY_ACCOUNTING_RECONCILE",
    ]);
    vi.mocked(evidenceHooks.useQboAccountingEvidence).mockReturnValue({
      data: source,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof evidenceHooks.useQboAccountingEvidence>);
    vi.mocked(evidenceHooks.useQboSourceBackedArSummary).mockReturnValue({
      data: { net_open_ar: "450.00", currency: "USD" },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof evidenceHooks.useQboSourceBackedArSummary>);
    vi.mocked(applicationHooks.useQboApplicationLedger).mockReturnValue({
      data: {
        source_evidence: {
          available: true,
          reason: null,
          acquired_at: "2026-10-01T12:00:00Z",
          total_source_records: 3,
          source_families: [],
        },
        families: [],
        last_execution: { total_dispositions: 0, last_applied_at: null },
        qbo_write_performed: false,
        accounting_posting_performed: false,
      },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<
      typeof applicationHooks.useQboApplicationLedger
    >);
    vi.mocked(applicationHooks.useQboReviewQueue).mockReturnValue({
      data: [
        {
          id: "review-1",
          source_family: "invoice",
          provider_record_id: "source-invoice-1",
          reference_number: "INV-101",
          source_date: "2026-09-01",
          source_amount: "600.00",
          source_entity_names: ["Sanitized Customer"],
          candidate_native_ids: [],
          conflicting_fields: ["amount"],
          exact_conflict: "Source and native amounts differ.",
          affected_dependents: [],
          provider_version: "1",
          allowed_actions: [
            { action: "HOLD_FOR_ACCOUNTANT", required_authority: "ACCOUNTANT" },
          ],
          current_decision: null,
          unlocks: 1,
          state: "OPEN",
        },
      ],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof applicationHooks.useQboReviewQueue>);
  });

  const renderRoute = () =>
    render(
      <MemoryRouter>
        <QboCutoverRoute />
      </MemoryRouter>,
    );

  it("shows source custody, cutoff, provenance, and limitations without credentials", () => {
    renderRoute();
    expect(
      screen.getByRole("heading", { name: "QuickBooks Cutover" }),
    ).toBeVisible();
    expect(screen.getByText(/3 records acquired/i)).toBeVisible();
    expect(screen.getByText("2026-09-30")).toBeVisible();
    expect(screen.getByText("Opening control not admitted")).toBeVisible();
    expect(
      screen.queryByText(/access token|client secret/i),
    ).not.toBeInTheDocument();
  });

  it("keeps unsupported opening authority unavailable and never manufactures a balanced package", () => {
    renderRoute();
    fireEvent.click(screen.getByRole("button", { name: "Opening Balances" }));
    expect(
      screen.getByText(
        /Opening Trial Balance review is not yet authoritative/i,
      ),
    ).toBeVisible();
    expect(
      screen.getByText(/not converted into debits or credits/i),
    ).toBeVisible();
    expect(
      screen.getByText(/No plug or unexplained difference is hidden/i),
    ).toBeVisible();
    expect(
      screen.queryByRole("button", { name: /approve/i }),
    ).not.toBeInTheDocument();
  });

  it("provides source A/R, A/P, and accountant exception drill-down without claiming a control tie", () => {
    renderRoute();
    fireEvent.click(screen.getByRole("button", { name: "A/R" }));
    expect(screen.getByText("$450.00")).toBeVisible();
    expect(screen.getByText("Sanitized Customer")).toBeVisible();
    expect(screen.getByText(/not an ACP control-account tie/i)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "A/P" }));
    expect(screen.getByText("Sanitized Vendor")).toBeVisible();
    expect(
      screen.getByText(/A\/P control reconciliation is unavailable/i),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Exceptions" }));
    expect(screen.getByText("Source and native amounts differ.")).toBeVisible();
    expect(screen.getByText(/Required authority: Accountant/i)).toBeVisible();
    expect(
      screen.getByRole("link", { name: /Open governed exception decisions/i }),
    ).toHaveAttribute("href", "/accounting/quickbooks-migration");
  });

  it("enforces report and reconciliation permissions", () => {
    permissions = new Set();
    const { rerender } = renderRoute();
    expect(
      screen.getByText(/Accounting report permission is required/i),
    ).toBeVisible();
    permissions = new Set(["COMPANY_ACCOUNTING_REPORT_READ"]);
    rerender(
      <MemoryRouter>
        <QboCutoverRoute />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Exceptions" }));
    expect(
      screen.getByText(/reconciliation permission is required/i),
    ).toBeVisible();
  });
});
