import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as hooks from "../hooks/useAccountingOperations";
import { AccountingRoute } from "./AccountingRoute";

let permissions = new Set<string>();
vi.mock("../auth", () => ({
  useHasPermission: (code: string) => permissions.has(code),
}));
vi.mock("../hooks/useAccountingOperations");

const query = (data: unknown) => ({
  data,
  isPending: false,
  isError: false,
  refetch: vi.fn(),
});
describe("AccountingRoute", () => {
  beforeEach(() => {
    permissions = new Set([
      "COMPANY_ACCOUNTING_READ",
      "COMPANY_ACCOUNTING_JOURNAL_PREPARE",
      "COMPANY_ACCOUNTING_JOURNAL_POST",
      "COMPANY_ACCOUNTING_PERIOD_MANAGE",
    ]);
    vi.mocked(hooks.useAccountingDashboard).mockReturnValue(
      query({
        account_count: 2,
        active_account_count: 2,
        open_period_count: 1,
        close_status: "OPEN",
        discrepancy_count: 0,
        operation_counts: {},
        trial_balance_debits: "100.00",
        trial_balance_credits: "100.00",
        balanced: true,
      }) as never,
    );
    vi.mocked(hooks.useAccountingAccounts).mockReturnValue(
      query([
        {
          id: "cash",
          company_id: "company",
          chart_version_id: "chart",
          code: "1000",
          name: "Cash",
          classification: "asset",
          normal_balance: "debit",
          status: "active",
          effective_from: "2026-11-01",
          effective_to: null,
        },
        {
          id: "revenue",
          company_id: "company",
          chart_version_id: "chart",
          code: "4000",
          name: "Revenue",
          classification: "revenue",
          normal_balance: "credit",
          status: "active",
          effective_from: "2026-11-01",
          effective_to: null,
        },
      ]) as never,
    );
    vi.mocked(hooks.useAccountingPeriods).mockReturnValue(
      query([
        {
          id: "period",
          company_id: "company",
          name: "November",
          start_date: "2026-11-01",
          end_date: "2026-11-30",
          status: "open",
          version: 1,
        },
      ]) as never,
    );
    vi.mocked(hooks.useAccountingJournals).mockReturnValue(query([]) as never);
    vi.mocked(hooks.useAccountingOperations).mockReturnValue(
      query([]) as never,
    );
    vi.mocked(hooks.useAccountingMutations).mockReturnValue({
      createJournal: { mutateAsync: vi.fn(), isPending: false },
      createOperation: { mutateAsync: vi.fn(), isPending: false },
      status: { mutateAsync: vi.fn(), isPending: false },
    } as never);
  });
  it("exposes the complete current accounting command center", () => {
    render(
      <MemoryRouter>
        <AccountingRoute />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("heading", { name: /accounting command center/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Chart of Accounts")).toBeInTheDocument();
    expect(screen.getByText("Controlled journal entry")).toBeInTheDocument();
    expect(
      screen.getByText("Current accounting operation"),
    ).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "deposit" })).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "fixed asset" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "tax accrual" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Period close" })).toHaveAttribute(
      "href",
      "/accounting/close",
    );
  });
  it("fails closed without accounting read authority", () => {
    permissions = new Set();
    render(
      <MemoryRouter>
        <AccountingRoute />
      </MemoryRouter>,
    );
    expect(
      screen.getByText(/not authorized to use Accounting/i),
    ).toBeInTheDocument();
  });
});
