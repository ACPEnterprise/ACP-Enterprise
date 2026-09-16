import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  useQboAccountingEvidence,
  useQboSourceBackedArSummary,
  useQboSourceBackedGeneralLedger,
  useQboSourceBackedProfitAndLoss,
} from "../../hooks/useQboAccountingEvidence";
import { QboSourceEvidence } from "./QboSourceEvidence";

vi.mock("../../hooks/useQboAccountingEvidence", () => ({
  useQboAccountingEvidence: vi.fn(),
  useQboSourceBackedArSummary: vi.fn(),
  useQboSourceBackedGeneralLedger: vi.fn(),
  useQboSourceBackedProfitAndLoss: vi.fn(),
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
  realm_company_identity: "c".repeat(64),
  source_company_label: "All County Plumbing and Leak Detection",
  source_company_id_masked: "…1234",
  company_info_verified_at: "2026-09-10T11:59:00Z",
  source_manifest_sha256: "d".repeat(64),
  completeness: "partial" as const,
  accounting_basis: "cash" as const,
  as_of: "2026-09-10T12:00:00Z",
  acquired_at: "2026-09-10T12:05:00Z",
  refresh_state: "stale" as const,
  provider_authorization: "unverified" as const,
  evidence_mode: "historical_snapshot" as const,
  entity_counts: { account: 1, invoice: 0, payment: 0 },
  page_counts: { account: 1 },
  catalog_dispositions: [
    {
      entity_kind: "time_activity",
      disposition: "PROVIDER_FAMILY_UNAVAILABLE",
    },
  ],
  snapshot_id: "snapshot-1",
  snapshot_digest: "a".repeat(64),
  limitations: ["HCP reconciliation remains separate."],
  accounts: [
    {
      source_id: "1",
      account_number: "1010",
      name: "Checking",
      fully_qualified_name: "Assets:Checking",
      account_type: "Bank",
      account_subtype: null,
      active: true,
      balance: unavailable,
    },
  ],
  invoices: [],
  bills: [],
  ar: {
    total_open: unavailable,
    invoice_evidence_count: 0,
    open_invoice_count: 0,
    closed_invoice_count: 0,
    current: unavailable,
    overdue: unavailable,
  },
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
      report_type: "balance_sheet",
      label: "Balance Sheet",
      basis: "cash" as const,
      start_date: null,
      as_of: "2026-09-10T12:00:00Z",
      acquired_at: "2026-09-10T12:05:00Z",
      source_digest: "f".repeat(64),
      state: "available" as const,
      limitation: null,
    },
  ],
  mutation_authority: "none" as const,
};

describe("QboSourceEvidence", () => {
  beforeEach(() => {
    vi.mocked(useQboSourceBackedGeneralLedger).mockReturnValue({
      isPending: false,
      isError: true,
      data: undefined,
    } as unknown as ReturnType<typeof useQboSourceBackedGeneralLedger>);
    vi.mocked(useQboSourceBackedArSummary).mockReturnValue({
      isLoading: false,
      data: undefined,
    } as unknown as ReturnType<typeof useQboSourceBackedArSummary>);
    vi.mocked(useQboSourceBackedProfitAndLoss).mockReturnValue({
      isPending: false,
      isError: false,
      data: {
        contract_version: "qbo-source-backed-financial-report/v1",
        report_type: "profit_and_loss",
        authority: "QBO_SOURCE_BACKED",
        provider_environment: "production",
        source: "QuickBooks Online",
        source_company: "All County Plumbing and Leak",
        realm_id: "9130357972400696",
        start_date: "2026-05-01",
        end_date: "2026-05-31",
        accounting_basis: "cash",
        currency: "USD",
        source_as_of: "2026-09-15T12:00:00Z",
        acquired_at: "2026-09-15T12:00:01Z",
        columns: ["Account", "Total"],
        rows: [{ kind: "summary", depth: 0, values: ["Net Income", "10.00"] }],
        source_digest: "e".repeat(64),
        accepted_as_acp_accounting: false,
        mutation_authority: "none",
      },
    } as unknown as ReturnType<typeof useQboSourceBackedProfitAndLoss>);
  });

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
      screen.getAllByText(/not posted ACP General Ledger truth/i).length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);
    expect(screen.queryByText("$0.00")).not.toBeInTheDocument();
    expect(
      screen.getByText(/HCP reconciliation remains separate/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/QBO, HCP, and ACP assertions remain separate/i),
    ).toBeVisible();
    expect(screen.getByText(/No winner selected/i)).toBeVisible();
    expect(screen.getByText(/Bill\/AP evidence is unavailable/i)).toBeVisible();
    expect(screen.getByText("QBO_SOURCE_BACKED")).toBeVisible();
    expect(
      screen.getByText(/Production realm 9130357972400696/i),
    ).toBeVisible();
    expect(screen.getByText(/accepted as ACP Accounting: no/i)).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "QuickBooks Source Center" }),
    ).toBeVisible();
    expect(
      screen.getByText("All County Plumbing and Leak Detection"),
    ).toBeVisible();
    expect(
      screen.getByText("General Ledger", { selector: "strong" }),
    ).toBeVisible();
    expect(screen.getByLabelText("Search source accounts")).toBeVisible();
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
