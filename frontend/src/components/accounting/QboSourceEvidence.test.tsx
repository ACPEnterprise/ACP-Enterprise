import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  useQboAccountingEvidence,
  useQboSourceBackedArSummary,
  useQboSourceBackedProfitAndLoss,
} from "../../hooks/useQboAccountingEvidence";
import { QboSourceEvidence } from "./QboSourceEvidence";

vi.mock("../../hooks/useQboAccountingEvidence", () => ({
  useQboAccountingEvidence: vi.fn(),
  useQboSourceBackedArSummary: vi.fn(),
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
      label: "Balance Sheet",
      basis: "cash" as const,
      as_of: "2026-09-10T12:00:00Z",
      state: "available" as const,
      limitation: null,
    },
  ],
  mutation_authority: "none" as const,
};

const historicalValue = {
  ...value,
  ar: {
    ...value.ar,
    total_open: {
      amount: "500584.34",
      currency: "USD",
      state: "available" as const,
    },
    invoice_evidence_count: 1341,
    open_invoice_count: 101,
  },
  historical_reconciliation: {
    state: "RECONCILED_WITH_DISCLOSED_EXCEPTIONS" as const,
    source_record_count: 20702,
    relationship_id_count: 97093,
    conflict_count: 7,
    customer_count: 909,
    invoice_count: 1341,
    invoice_line_count: 3140,
    invoice_open_balance: {
      amount: "500584.34",
      currency: "USD",
      state: "available" as const,
    },
    payment_count: 1237,
    payment_total: {
      amount: "1523656.97",
      currency: "USD",
      state: "available" as const,
    },
    payment_invoice_links: 1171,
    missing_payment_invoice_links: 0,
    unlinked_payment_count: 73,
    unlinked_payment_total: {
      amount: "85414.91",
      currency: "USD",
      state: "available" as const,
    },
    provider_unapplied_amount: {
      amount: "87544.91",
      currency: "USD",
      state: "available" as const,
    },
    controls: {},
    mutation_authority: "none" as const,
  },
  payments: [
    {
      source_id: "payment-1",
      transaction_date: "2026-11-19",
      customer_label: "Acceptance Customer",
      source_status: "received",
      amount: {
        amount: "125.00",
        currency: "USD",
        state: "available" as const,
      },
      application_state: "applied",
      applied_document_ids: ["invoice-1"],
    },
  ],
};

describe("QboSourceEvidence", () => {
  beforeEach(() => {
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
    expect(screen.getByText("QBO_SOURCE_BACKED")).toBeVisible();
    expect(
      screen.getByText(/Production realm 9130357972400696/i),
    ).toBeVisible();
    expect(screen.getByText(/accepted as ACP Accounting: no/i)).toBeVisible();
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

  it("labels archive A/R truthfully and exposes reconciliation evidence", () => {
    vi.mocked(useQboAccountingEvidence).mockReturnValue({
      isPending: false,
      isError: false,
      data: historicalValue,
    } as unknown as ReturnType<typeof useQboAccountingEvidence>);
    vi.mocked(useQboSourceBackedArSummary).mockReturnValue({
      isLoading: false,
      data: {
        contract_version: "qbo-source-backed-ar-summary/v1",
        authority: "QBO_SOURCE_BACKED",
        provider_environment: "production",
        source: "QuickBooks Online manual archive A/R evidence",
        source_company: "All County Plumbing and Leak",
        realm_id: "masked",
        report_date: "2026-11-27",
        currency: "USD",
        source_as_of: "2026-11-19",
        acquired_at: "2026-11-20T00:06:49Z",
        net_open_ar: "500584.34",
        includes_customer_credits_and_unapplied_payments: false,
        source_digest: "f".repeat(64),
        accepted_as_acp_accounting: false,
        mutation_authority: "none",
      },
    } as unknown as ReturnType<typeof useQboSourceBackedArSummary>);

    render(<QboSourceEvidence enabled />);

    expect(screen.getByText("20,702")).toBeVisible();
    expect(screen.getByText("97,093")).toBeVisible();
    expect(screen.getByText("Archive open invoice balance")).toBeVisible();
    expect(
      screen.getByText(/credits and unapplied payments require/i),
    ).toBeVisible();
    expect(screen.queryByText("Real total open A/R")).not.toBeInTheDocument();
    expect(screen.getByText("Acceptance Customer")).toBeVisible();
    expect(screen.getByText("payment-1")).toBeVisible();
  });

  it("fails closed and supports a read-only retry when A/R evidence is unavailable", () => {
    const refetch = vi.fn();
    vi.mocked(useQboAccountingEvidence).mockReturnValue({
      isPending: false,
      isError: false,
      data: historicalValue,
    } as unknown as ReturnType<typeof useQboAccountingEvidence>);
    vi.mocked(useQboSourceBackedArSummary).mockReturnValue({
      isLoading: false,
      isError: true,
      data: undefined,
      refetch,
    } as unknown as ReturnType<typeof useQboSourceBackedArSummary>);

    render(<QboSourceEvidence enabled />);

    expect(screen.getByText(/No balance was inferred/i)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry read-only A/R" }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("navigates to source-backed report detail with provenance and no posting claim", () => {
    vi.mocked(useQboAccountingEvidence).mockReturnValue({
      isPending: false,
      isError: false,
      data: value,
    } as unknown as ReturnType<typeof useQboAccountingEvidence>);
    render(<QboSourceEvidence enabled />);
    fireEvent.click(screen.getByRole("button", { name: "Open Balance Sheet" }));
    const detail = screen.getByRole("region", { name: "QBO historical report detail" });
    expect(detail).toHaveTextContent("balance-sheet");
    expect(detail).toHaveTextContent("QBO SOURCE BACKED");
    expect(detail).toHaveTextContent(/accepted as ACP Accounting: no/i);
    expect(detail).toHaveTextContent(/no posting authority/i);
  });
});
