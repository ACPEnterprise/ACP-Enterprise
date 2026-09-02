import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BusinessEconomicsRoute } from "./BusinessEconomicsRoute";

let allowed = false;
let cashAllowed = false;
let workspaceEnabled: boolean | undefined;
let detailEnabled: boolean | undefined;
let workspaceMode: "success" | "error" | "pending" = "success";
const refetch = vi.fn();
vi.mock("../auth", () => ({
  useHasPermission: (permission: string) =>
    permission === "COMPANY_ECONOMICS_MEASUREMENT_READ" ? allowed : cashAllowed,
}));
vi.mock("../hooks/useBusinessEconomics", () => ({
  useCashOperationalEconomics: () => ({
    isPending: false,
    isError: false,
    data: {
      work_period: {
        state: "COMPLETE",
        currency: "USD",
        earned_revenue_minor: 100000,
        job_contribution_minor: 50000,
        job_count: 2,
        complete_job_count: 1,
        limitation: "Work is not proof of collection.",
      },
      operational_current_state: {
        state: "AVAILABLE",
        currency: "USD",
        completed_jobs_with_open_invoice_count: 1,
        completed_work_open_commercial_balance_minor: 25000,
        payment_receipt_count: 1,
        payment_receipt_assertion_minor: 75000,
        deposit_batch_count: 0,
        deposit_batch_gross_minor: 0,
        open_vendor_obligation_count: 1,
        open_vendor_obligation_minor: 10000,
        vendor_disbursement_count: 0,
        vendor_disbursement_minor: 0,
        limitations: [],
      },
      cash_accounting_period: {
        state: "EXTERNAL_GATE",
        basis: "cash",
        currency: "USD",
        recognized_income_minor: null,
        recognized_expense_minor: null,
        limitation: "Accounting reports are required.",
      },
    },
  }),
  useOwnerIntelligence: () => ({
    isPending: false,
    isError: false,
    data: {
      answer: { kind: "period_comparison" },
      context_packet: {
        classification: "INCOMPLETE",
        completeness: "partial",
        limitations: ["economic_evidence_is_not_complete"],
        source_references: [],
        evidence_digest: "a".repeat(64),
      },
    },
  }),
  useEconomicsResult: (_id: string | null, enabled: boolean) => {
    detailEnabled = enabled;
    return { isPending: false, isError: false, data: null };
  },
  useEconomicsWorkspace: (_start: string, _end: string, enabled: boolean) => {
    workspaceEnabled = enabled;
    if (workspaceMode === "pending")
      return { isPending: true, isError: false, data: null, refetch };
    if (workspaceMode === "error")
      return { isPending: false, isError: true, data: null, refetch };
    return {
      isPending: false,
      isError: false,
      refetch,
      data: {
        period: { start: "2027-01-01", end: "2027-01-31" },
        prior_period: { start: "2026-12-01", end: "2026-12-31" },
        quality_state: "partial",
        currency: "USD",
        source_result_count: 2,
        excluded_job_count: 0,
        job_count: 2,
        complete_job_count: 1,
        unclassified_job_count: 1,
        totals: {
          revenue: 100000,
          labor: 30000,
          materials: 20000,
          equipment: 0,
          truck: 0,
          overhead: 0,
          gross_profit: 50000,
          net_profit: 50000,
        },
        jobs: [],
        service_categories: [],
        customers: [],
        branches: [],
        fully_allocated_available: false,
        explanation: "Incomplete Jobs remain visible.",
        comparison: {
          state: "unavailable",
          reason: "Prior evidence is incomplete.",
        },
        readiness: {
          evidence: "partial",
          allocation_policy: "policy_required",
          attribution: "partial",
          allocation_authority: {
            state: "policy_required",
            pool_policy: "unconfigured",
            basis_policy: "unconfigured",
            source_evidence: "insufficient_source",
            supported_basis_types: ["labor_hours", "revenue"],
            owner_decision:
              "Select approved cost pools, source evidence, and an allocation basis; no default is applied.",
            callback_economics: "external_gate",
          },
          policy_gaps: [],
        },
        beacon_conditions: [
          { kind: "incomplete_economic_evidence", state: "partial" },
        ],
        owner_question_acceptance: {
          version: "economics.owner-question-acceptance.v1",
          matrix_digest: "b".repeat(64),
          mutation_authority: "none",
          questions: [
            {
              key: "work",
              question: "How much work did we perform?",
              disposition: "PARTIALLY_ANSWERABLE",
              answer_source: "earned_work",
              owning_domains: ["Business Economics"],
              inspect_path: "/business-economics",
              missing_permissions: [],
              why: "ACP can answer part of this question, but evidence is partial.",
              what_resolves_it: null,
              limitation: null,
            },
            {
              key: "collected",
              question: "How much have we collected?",
              disposition: "EXTERNAL_GATE",
              answer_source: "accounting_cash",
              owning_domains: ["Accounting"],
              inspect_path: "/financial-reports",
              missing_permissions: [],
              why: "Admitted cash-basis Accounting totals are required.",
              what_resolves_it: "Wait for the owning domain to admit authoritative evidence.",
              limitation: "Payment assertions are not cash truth.",
            },
          ],
        },
      },
    };
  },
}));

describe("BusinessEconomicsRoute", () => {
  beforeEach(() => {
    allowed = false;
    cashAllowed = false;
    workspaceMode = "success";
    workspaceEnabled = undefined;
    detailEnabled = undefined;
    refetch.mockReset();
  });
  it("fails closed without Economics read authority or issuing the query", () => {
    render(<BusinessEconomicsRoute />);
    expect(screen.getByText(/not authorized/i)).toBeVisible();
    expect(workspaceEnabled).toBe(false);
    expect(detailEnabled).toBe(false);
  });
  it("shows truthful partial, no-policy, and distinct work/obligation/cash states", () => {
    allowed = true;
    cashAllowed = true;
    render(<BusinessEconomicsRoute />);
    expect(screen.getByText(/Evidence partial/i)).toBeVisible();
    expect(
      screen.getAllByText(/fully allocated profitability is unavailable/i)
        .length,
    ).toBeGreaterThan(0);
    expect(screen.getByText(/no default is applied/i)).toBeVisible();
    expect(
      screen.getByRole("option", { name: /what prevents full profitability/i }),
    ).toBeVisible();
    expect(
      screen.getByRole("option", { name: /what should i inspect first/i }),
    ).toBeVisible();
    expect(screen.getByText(/Three related truths/i)).toBeVisible();
    expect(screen.getByText(/Work performed/i)).toBeVisible();
    expect(screen.getByText(/Still owed/i)).toBeVisible();
    expect(
      screen.getByRole("heading", { name: /Cash-basis Accounting/i }),
    ).toBeVisible();
    expect(screen.getAllByText("$1,000.00").length).toBeGreaterThan(0);
    expect(screen.getByText("$250.00")).toBeVisible();
    expect(screen.getByText("Unavailable")).toBeVisible();
    expect(screen.getByText(/What ACP can answer/i)).toBeVisible();
    expect(screen.getByText(/partially answerable/i)).toBeVisible();
    expect(screen.getAllByText(/external gate/i).length).toBeGreaterThan(0);
  });
  it("keeps cross-domain cash and obligation amounts behind every owning permission", () => {
    allowed = true;
    cashAllowed = false;
    render(<BusinessEconomicsRoute />);
    expect(
      screen.getByText(
        /requires each domain's explicit report-read authority/i,
      ),
    ).toBeVisible();
    expect(screen.queryByText("$250.00")).not.toBeInTheDocument();
  });
  it("offers a safe retry when Economics is temporarily unavailable", async () => {
    allowed = true;
    workspaceMode = "error";
    render(<BusinessEconomicsRoute />);
    expect(screen.getByText(/no value was inferred/i)).toBeVisible();
    await userEvent.click(
      screen.getByRole("button", { name: /retry economics/i }),
    );
    expect(refetch).toHaveBeenCalledOnce();
  });
});
