import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuth } from "../auth/useAuth";
import { useEffectivePermissions } from "../auth/usePermissions";
import { useAnalyticsSummary } from "../hooks/useAnalyticsSummary";
import { useEconomicsMeasurementFoundation } from "../hooks/useBusinessEconomics";
import { useDispatchBoard } from "../hooks/useDispatch";
import { useReceivablesSummary } from "../hooks/useInvoices";
import { useCompletedJobTrend } from "../hooks/useJobs";
import { useMoneyPosition } from "../hooks/usePayments";
import { CommandCenterRoute } from "./CommandCenterRoute";

vi.mock("../auth/useAuth");
vi.mock("../auth/usePermissions");
vi.mock("../hooks/useAnalyticsSummary");
vi.mock("../hooks/useBusinessEconomics");
vi.mock("../hooks/useDispatch");
vi.mock("../hooks/useInvoices");
vi.mock("../hooks/useJobs");
vi.mock("../hooks/usePayments");

const permissions = new Set([
  "COMPANY_INVOICE_READ",
  "COMPANY_JOB_READ",
  "COMPANY_DISPATCH_READ",
  "COMPANY_ANALYTICS_READ",
  "COMPANY_ECONOMICS_MEASUREMENT_READ",
  "COMPANY_PAYMENT_READ",
]);

function queryResult<T>(data: T) {
  return { data, isPending: false, isLoading: false, isError: false } as never;
}

function arrange() {
  vi.mocked(useAuth).mockReturnValue({
    activeCompany: {
      id: "company-1",
      name: "All County Plumbing & Leak",
      code: "ACP",
      membership_id: "membership-1",
      default_branch_id: "branch-1",
      has_all_branch_access: true,
      branches: [
        { id: "branch-1", name: "Main", code: "MAIN", is_primary: true },
      ],
    },
  } as ReturnType<typeof useAuth>);
  vi.mocked(useEffectivePermissions).mockReturnValue(permissions);
  vi.mocked(useReceivablesSummary).mockReturnValue(
    queryResult({
      as_of: "2026-09-22",
      generated_at: "2026-09-22T12:00:00Z",
      branch_id: null,
      currency: "USD",
      evidence_state: "AVAILABLE",
      open_invoice_count: 4,
      total_open_amount: "2400.00",
      due_today_amount: "500.00",
      buckets: [
        {
          key: "not_due",
          label: "Current / Not Due",
          invoice_count: 2,
          amount: "1000.00",
        },
        {
          key: "due_today",
          label: "Due Today",
          invoice_count: 1,
          amount: "500.00",
        },
        {
          key: "past_due_1_15",
          label: "1–15 Days Past Due",
          invoice_count: 1,
          amount: "900.00",
        },
        {
          key: "past_due_16_30",
          label: "16–30 Days Past Due",
          invoice_count: 0,
          amount: "0.00",
        },
        {
          key: "past_due_31_plus",
          label: "31+ Days Past Due",
          invoice_count: 0,
          amount: "0.00",
        },
      ],
    }),
  );
  vi.mocked(useCompletedJobTrend).mockReturnValue(
    queryResult({
      generated_at: "2026-09-22T12:00:00Z",
      timezone: "America/New_York",
      branch_id: null,
      currency: "USD",
      granularity: "day",
      period_start: "2026-09-22",
      period_end: "2026-09-22",
      points: [
        {
          label: "Sep 22",
          period_start: "2026-09-22",
          period_end: "2026-09-22",
          completed_start_at: "2026-09-22T04:00:00Z",
          completed_end_at: "2026-09-23T04:00:00Z",
          job_count: 3,
          produced_value: "1500.00",
          known_produced_value: "1500.00",
          missing_value_count: 0,
          evidence_state: "AVAILABLE",
        },
      ],
    }),
  );
  vi.mocked(useDispatchBoard).mockReturnValue(
    queryResult({
      total_count: 1,
      items: [
        {
          appointment_id: "appointment-1",
          appointment_number: "APT-000001",
          job_id: "job-1",
          job_number: "JOB-000001",
          customer_display_name: "Hammer Haag",
          service_location_label: "100 Main St",
          branch_id: "branch-1",
          status: "confirmed",
          window_start_at: "2026-09-22T13:00:00Z",
          window_end_at: "2026-09-22T15:00:00Z",
          assignment: {
            primary_employee_id: "employee-1",
            primary_employee_name: "Mel Santiago",
          },
        },
      ],
    }),
  );
  vi.mocked(useAnalyticsSummary).mockReturnValue(
    queryResult({
      period_start: "2026-09-22T04:00:00Z",
      period_end: "2026-09-23T04:00:00Z",
      timezone: "America/New_York",
      cash_collected: { name: "Cash collected", value: "750.00" },
      booked_revenue: { name: "Booked revenue", value: "0" },
      new_customers: { name: "New customers", value: 2 },
      appointments_booked: { name: "Appointments", value: 4 },
      total_events: { name: "Events", value: 6 },
      recent_activity: [],
    }),
  );
  vi.mocked(useEconomicsMeasurementFoundation).mockReturnValue(
    queryResult({
      contract_version: "1",
      company_id: "company-1",
      branch_id: null,
      canonical_efficiency_kpi: null,
      break_even_input_readiness: {},
      mutation_authority: "none",
    }),
  );
  vi.mocked(useMoneyPosition).mockReturnValue(
    queryResult({
      company_id: "company-1",
      branch_id: null,
      period_start: "2026-09-22",
      period_end: "2026-09-22",
      as_of: "2026-09-22",
      generated_at: "2026-09-22T12:00:00Z",
      bank_balance: {
        amount: null,
        currency: null,
        evidence_state: "UNAVAILABLE",
        limitation: "No sanctioned authoritative bank-balance source is connected.",
        connection_state: "NOT_CONNECTED",
        provider_as_of: null,
        last_sync_at: null,
      },
      accounts_receivable_due_today: {
        amount: "500.00",
        currency: "USD",
        evidence_state: "AVAILABLE",
        limitation: null,
        invoice_count: 1,
        drilldown_path: "/invoices?agingBucket=due_today&asOf=2026-09-22",
      },
      cod_expected_today: {
        amount: null,
        currency: null,
        evidence_state: "UNAVAILABLE",
        limitation: "Scheduled COD value is not authoritative.",
      },
      expected_collections_today: {
        amount: null,
        currency: null,
        evidence_state: "INCOMPLETE",
        limitation: "COD evidence is incomplete.",
      },
      card_processing: {
        transaction_count: 2,
        amount_charged: {
          amount: "640.00",
          currency: "USD",
          evidence_state: "AVAILABLE",
          limitation: null,
        },
        refund_amount: {
          amount: "0.00",
          currency: "USD",
          evidence_state: "AVAILABLE",
          limitation: null,
        },
        chargeback_amount: {
          amount: "0.00",
          currency: "USD",
          evidence_state: "AVAILABLE",
          limitation: null,
        },
        fees_paid: {
          amount: null,
          currency: null,
          evidence_state: "UNAVAILABLE",
          limitation: "No provider settlement evidence is available.",
        },
        effective_fee_rate: null,
        limitation: "Settlement fees are not allocated to charges.",
      },
      collection_state: {
        collected: {
          amount: "750.00",
          currency: "USD",
          evidence_state: "AVAILABLE",
          limitation: null,
        },
        settled_gross: {
          amount: null,
          currency: null,
          evidence_state: "UNAVAILABLE",
          limitation: "No provider settlement evidence is available.",
        },
        settled_net: {
          amount: null,
          currency: null,
          evidence_state: "UNAVAILABLE",
          limitation: "No provider settlement evidence is available.",
        },
        deposited: {
          amount: null,
          currency: null,
          evidence_state: "UNAVAILABLE",
          limitation: "No bank-confirmed deposit evidence is available.",
        },
      },
    }),
  );
}

describe("CommandCenterRoute", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    arrange();
  });

  it("renders authoritative money and job evidence while keeping unavailable facts distinct from zero", () => {
    render(
      <MemoryRouter>
        <CommandCenterRoute />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("heading", { name: "Command Center" }),
    ).toBeInTheDocument();
    const moneyPanel = screen
      .getByRole("heading", { name: "Money / Cash Position" })
      .closest("article");
    expect(moneyPanel).toHaveClass("twelve-hats-panel-outline");
    expect(moneyPanel).toHaveAttribute("data-panel-tone", "normal");
    expect(screen.getByText("$2,400")).toBeInTheDocument();
    expect(screen.getByText(/Due-today AR: \$500/)).toBeInTheDocument();
    expect(screen.getByText("Not connected")).toBeInTheDocument();
    const economicStatus = screen
      .getByText("Economic Health unavailable")
      .closest("[data-economic-status]");
    expect(economicStatus).toHaveAttribute(
      "data-economic-status",
      "UNAVAILABLE",
    );
    expect(economicStatus).toHaveClass("border-2", "border-dashed");
    expect(economicStatus).not.toHaveClass("twelve-hats-panel-outline");
    expect(screen.getByText(/Hammer Haag/)).toBeInTheDocument();
    expect(screen.getByText("$640")).toBeInTheDocument();
    expect(screen.getByText("No provider settlement evidence is available.")).toBeInTheDocument();
    const bankTile = screen.getByText("Bank cash / available").parentElement;
    expect(bankTile).not.toBeNull();
    expect(
      within(bankTile!).queryByText("$0", { exact: true }),
    ).not.toBeInTheDocument();
  });

  it("preserves exact AR and graph drill-down filters", () => {
    render(
      <MemoryRouter>
        <CommandCenterRoute />
      </MemoryRouter>,
    );
    const dueToday = screen.getByRole("link", { name: /Due Today/ });
    expect(dueToday).toHaveAttribute(
      "href",
      expect.stringContaining("agingBucket=due_today"),
    );
    const point = screen.getAllByRole("link", { name: /Sep 22: \$1,500/ })[0];
    expect(point).toHaveAttribute(
      "href",
      expect.stringContaining("completedStartAt=2026-09-22T04%3A00%3A00Z"),
    );
    expect(point).toHaveAttribute(
      "href",
      expect.stringContaining("status=completed"),
    );
  });

  it("switches date and branch scope without inventing branch analytics", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <CommandCenterRoute />
      </MemoryRouter>,
    );
    await user.click(screen.getByRole("button", { name: "Tomorrow" }));
    expect(useDispatchBoard).toHaveBeenLastCalledWith(
      expect.any(String),
      expect.any(String),
      undefined,
      true,
    );
    await user.selectOptions(
      screen.getByLabelText("Command Center Branch"),
      "branch-1",
    );
    expect(useReceivablesSummary).toHaveBeenLastCalledWith(
      expect.any(String),
      "branch-1",
      true,
    );
    expect(useCompletedJobTrend).toHaveBeenLastCalledWith(
      expect.any(String),
      expect.any(String),
      expect.any(String),
      "branch-1",
      true,
    );
    expect(useAnalyticsSummary).toHaveBeenLastCalledWith(false);
    expect(useMoneyPosition).toHaveBeenLastCalledWith(
      expect.any(String),
      expect.any(String),
      expect.any(String),
      "branch-1",
      true,
    );
  });

  it("enforces domain read permissions at every data request", () => {
    vi.mocked(useEffectivePermissions).mockReturnValue(new Set());
    render(
      <MemoryRouter>
        <CommandCenterRoute />
      </MemoryRouter>,
    );
    expect(useReceivablesSummary).toHaveBeenCalledWith(
      expect.any(String),
      undefined,
      false,
    );
    expect(useCompletedJobTrend).toHaveBeenCalledWith(
      expect.any(String),
      expect.any(String),
      expect.any(String),
      undefined,
      false,
    );
    expect(useDispatchBoard).toHaveBeenCalledWith(
      expect.any(String),
      expect.any(String),
      undefined,
      false,
    );
    expect(useAnalyticsSummary).toHaveBeenCalledWith(false);
    expect(useEconomicsMeasurementFoundation).toHaveBeenCalledWith(false);
    expect(useMoneyPosition).toHaveBeenCalledWith(
      expect.any(String),
      expect.any(String),
      expect.any(String),
      undefined,
      false,
    );
  });
});
