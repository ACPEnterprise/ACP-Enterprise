import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AccountingCloseWorkspaceRoute } from "./AccountingCloseWorkspaceRoute";
import * as closeHooks from "../hooks/useAccountingClose";
import * as evidenceHooks from "../hooks/useQboAccountingEvidence";
import * as applicationHooks from "../hooks/useQboNativeApplication";
import * as payrollHooks from "../hooks/usePayroll";

let permissions = new Set([
  "COMPANY_ACCOUNTING_REPORT_READ",
  "COMPANY_ACCOUNTING_RECONCILE",
  "COMPANY_ACCOUNTING_PERIOD_MANAGE",
  "COMPANY_ACCOUNTING_FINANCE_APPROVE",
]);
vi.mock("../auth", () => ({
  useHasPermission: (permission: string) => permissions.has(permission),
}));
vi.mock("../hooks/useAccountingClose");
vi.mock("../hooks/useQboAccountingEvidence");
vi.mock("../hooks/useQboNativeApplication");
vi.mock("../hooks/usePayroll");

describe("AccountingCloseWorkspaceRoute", () => {
  beforeEach(() => {
    permissions = new Set([
      "COMPANY_ACCOUNTING_REPORT_READ",
      "COMPANY_ACCOUNTING_RECONCILE",
      "COMPANY_ACCOUNTING_PERIOD_MANAGE",
      "COMPANY_ACCOUNTING_FINANCE_APPROVE",
    ]);
    vi.mocked(closeHooks.useAccountingPeriods).mockReturnValue({
      data: [
        {
          id: "period-1",
          company_id: "company-1",
          name: "September 2026",
          start_date: "2026-09-01",
          end_date: "2026-09-30",
          status: "closing",
          version: 2,
        },
      ],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof closeHooks.useAccountingPeriods>);
    vi.mocked(closeHooks.useReportComparisons).mockReturnValue({
      data: [
        "trial_balance",
        "profit_and_loss",
        "balance_sheet",
        "general_ledger",
        "ar_aging",
        "ap_aging",
        "cash_flow",
        "job_costing",
      ].map((family) => ({
        family,
        acp_available: family !== "cash_flow",
        qbo_available: family === "profit_and_loss",
        state: family === "profit_and_loss" ? "COMPARABLE" : "UNAVAILABLE",
        non_comparable_reasons:
          family === "cash_flow" ? ["QBO_EVIDENCE_UNAVAILABLE"] : [],
        start_date: "2026-09-01",
        end_date: "2026-09-30",
        cutoff: "2026-09-30T23:59:59Z",
        basis: "accrual",
        currency: "USD",
        acp_provenance: ["ACP ledger v1"],
        qbo_provenance:
          family === "profit_and_loss" ? ["QBO sealed report v1"] : [],
        acp_total: family === "profit_and_loss" ? "100.00" : null,
        qbo_total: family === "profit_and_loss" ? "90.00" : null,
        difference: family === "profit_and_loss" ? "10.00" : null,
        acp_total_debits: null,
        acp_total_credits: null,
        qbo_total_debits: null,
        qbo_total_credits: null,
        acp_balanced: null,
        qbo_balanced: null,
        lines: [],
        review_state: "OPEN",
        evidence_digest: "d".repeat(64),
      })),
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof closeHooks.useReportComparisons>);
    vi.mocked(closeHooks.useAccountantReview).mockReturnValue({
      data: {
        company_id: "company-1",
        generated_at: "2026-10-03T12:00:00Z",
        items: [
          {
            source_domain: "qbo_application",
            source_reference: "review-1",
            category: "amount_difference",
            state: "OPEN",
            review_requirement: "Accountant review required",
            display_identity: "Invoice INV-101",
            provenance: ["QBO sealed evidence"],
            source_lifecycle: "REVIEW_REQUIRED",
            action_path: "/accounting/quickbooks-migration",
          },
          {
            source_domain: "opening_control",
            source_reference: "opening-1",
            category: "opening_equity",
            state: "READY_FOR_REVIEW",
            review_requirement: "Classify unexplained opening equity",
            display_identity: "September opening package",
            provenance: ["Sealed QBO Trial Balance"],
            source_lifecycle: "REVIEW_REQUIRED",
            action_path: "/accounting/quickbooks-cutover",
          },
        ],
      },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof closeHooks.useAccountantReview>);
    vi.mocked(closeHooks.usePeriodCloseReadiness).mockReturnValue({
      data: {
        period_id: "period-1",
        start_date: "2026-09-01",
        end_date: "2026-09-30",
        lifecycle_status: "closing",
        accounting_basis: "accrual",
        currency: "USD",
        opening_equity_readiness: "BLOCKED",
        trial_balance_readiness: "READY",
        ar_readiness: "BLOCKED",
        ap_readiness: "BLOCKED",
        payroll_readiness: "BLOCKED",
        report_comparison_readiness: "BLOCKED",
        accountant_review_blocker_count: 1,
        required_approvals: ["FINANCE_APPROVE"],
        blockers: [
          {
            code: "PAYROLL_EVIDENCE_UNAVAILABLE",
            family: "PAYROLL",
            state: "UNAVAILABLE",
            explanation: "Approved Payroll posting evidence is unavailable.",
            evidence_reference: null,
          },
        ],
        overall_readiness: "BLOCKED",
        evidence_digest: "e".repeat(64),
        generated_at: "2026-10-03T12:00:00Z",
      },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof closeHooks.usePeriodCloseReadiness>);
    vi.mocked(closeHooks.useGovernedPeriodClose).mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      isError: false,
      isSuccess: false,
    } as unknown as ReturnType<typeof closeHooks.useGovernedPeriodClose>);
    vi.mocked(evidenceHooks.useQboAccountingEvidence).mockReturnValue({
      data: {
        as_of: "2026-09-30T23:59:59Z",
        accounting_basis: "accrual",
        reports: [
          {
            report_key: "pnl",
            label: "Profit and Loss",
            basis: "accrual",
            as_of: "2026-09-30",
            state: "available",
            limitation: null,
          },
        ],
      },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof evidenceHooks.useQboAccountingEvidence>);
    vi.mocked(applicationHooks.useQboApplicationLedger).mockReturnValue({
      data: { source_evidence: { source_run_id: null } },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<
      typeof applicationHooks.useQboApplicationLedger
    >);
    vi.mocked(closeHooks.useOpeningControlDetail).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof closeHooks.useOpeningControlDetail>);
    vi.mocked(closeHooks.usePayrollAccountingControl).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof closeHooks.usePayrollAccountingControl>);
    vi.mocked(payrollHooks.usePayrollOperatingRegisters).mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<
      typeof payrollHooks.usePayrollOperatingRegisters
    >);
  });

  const renderRoute = () =>
    render(
      <MemoryRouter>
        <AccountingCloseWorkspaceRoute />
      </MemoryRouter>,
    );

  it("shows all canonical report families and withholds unavailable differences", () => {
    renderRoute();
    expect(
      screen.getByRole("heading", { name: "Accountant close workspace" }),
    ).toBeVisible();
    expect(screen.getByText("Profit & Loss")).toBeVisible();
    expect(screen.getByText("Cash Flow")).toBeVisible();
    expect(screen.getByText("Job Costing")).toBeVisible();
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(1);
    expect(screen.getByText("$10.00")).toBeVisible();
  });

  it("unifies canonical review items and normal workspace handoffs", () => {
    renderRoute();
    expect(screen.getByText("Invoice INV-101")).toBeVisible();
    expect(screen.getByText("September opening package")).toBeVisible();
    expect(
      screen.getAllByRole("link", { name: /Open governed workflow/i })[0],
    ).toHaveAttribute("href", "/accounting/quickbooks-migration");
    expect(
      screen.getByRole("link", { name: /Open Payroll review/i }),
    ).toHaveAttribute("href", "/payroll");
  });

  it("shows canonical period blockers and withholds close while blocked", () => {
    renderRoute();
    expect(
      screen.getByRole("option", { name: /September 2026/i }),
    ).toBeVisible();
    expect(
      screen.getByText(/Approved Payroll posting evidence is unavailable/i),
    ).toBeVisible();
    expect(
      screen.queryByRole("button", { name: /close period/i }),
    ).not.toBeInTheDocument();
  });

  it("explains server-declared comparability mismatches without calculating a value", () => {
    vi.mocked(closeHooks.useReportComparisons).mockReturnValue({
      data: [
        {
          family: "trial_balance",
          acp_available: true,
          qbo_available: true,
          state: "NOT_COMPARABLE",
          non_comparable_reasons: [
            "CUTOFF_MISMATCH",
            "ACCOUNTING_BASIS_MISMATCH",
            "CURRENCY_MISMATCH",
            "BRANCH_SCOPE_MISMATCH",
            "REPORT_VERSION_MISMATCH",
          ],
          start_date: null,
          end_date: "2026-09-30",
          cutoff: null,
          basis: null,
          currency: null,
          acp_provenance: ["ACP v2"],
          qbo_provenance: ["QBO v1"],
          acp_total: null,
          qbo_total: null,
          difference: null,
          acp_total_debits: "100.00",
          acp_total_credits: "100.00",
          qbo_total_debits: "101.00",
          qbo_total_credits: "100.00",
          acp_balanced: true,
          qbo_balanced: false,
          lines: [
            {
              identity: "retained",
              label: "Retained Earnings",
              acp_classification: "retained_earnings",
              qbo_classification: "opening_equity",
              acp_amount: "100.00",
              qbo_amount: "101.00",
              difference: null,
              acp_debit: null,
              acp_credit: "100.00",
              qbo_debit: null,
              qbo_credit: "101.00",
              disposition: "REVIEW_REQUIRED",
            },
          ],
          review_state: "REVIEW_REQUIRED",
          evidence_digest: "c".repeat(64),
        },
      ],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof closeHooks.useReportComparisons>);
    renderRoute();
    expect(screen.getByText("Cutoff mismatch")).toBeVisible();
    expect(screen.getByText("Accounting basis mismatch")).toBeVisible();
    expect(screen.getByText("Currency mismatch")).toBeVisible();
    expect(screen.getByText("Branch scope mismatch")).toBeVisible();
    expect(screen.getByText("Report version mismatch")).toBeVisible();
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(1);
    fireEvent.click(screen.getByText(/Trial Balance supporting lines/i));
    expect(screen.getByText("Balanced")).toBeVisible();
    expect(screen.getByText("Unbalanced")).toBeVisible();
    expect(screen.getByText("Retained earnings")).toBeVisible();
    expect(screen.getAllByText("Opening equity").length).toBeGreaterThan(1);
  });

  it("shows a governed close action only for current READY evidence and authorization", () => {
    const mutateAsync = vi.fn().mockResolvedValue({ status: "closed" });
    vi.mocked(closeHooks.useGovernedPeriodClose).mockReturnValue({
      mutateAsync,
      isPending: false,
      isError: false,
      isSuccess: false,
    } as unknown as ReturnType<typeof closeHooks.useGovernedPeriodClose>);
    vi.mocked(closeHooks.usePeriodCloseReadiness).mockReturnValue({
      data: {
        period_id: "period-1",
        start_date: "2026-09-01",
        end_date: "2026-09-30",
        lifecycle_status: "closing",
        accounting_basis: "accrual",
        currency: "USD",
        opening_equity_readiness: "READY",
        trial_balance_readiness: "READY",
        ar_readiness: "READY",
        ap_readiness: "READY",
        payroll_readiness: "READY",
        report_comparison_readiness: "READY",
        accountant_review_blocker_count: 0,
        required_approvals: ["FINANCE_APPROVE"],
        blockers: [],
        overall_readiness: "READY",
        evidence_digest: "r".repeat(64),
        generated_at: "2026-10-03T12:00:00Z",
      },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof closeHooks.usePeriodCloseReadiness>);
    renderRoute();
    const close = screen.getByRole("button", { name: "Close period" });
    expect(close).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Close reason"), {
      target: { value: "September reviewed" },
    });
    fireEvent.click(close);
    expect(mutateAsync).toHaveBeenCalledWith({
      periodId: "period-1",
      expectedVersion: 2,
      reason: "September reviewed",
    });
  });

  it("renders an empty canonical review queue without implying approval", () => {
    vi.mocked(closeHooks.useAccountantReview).mockReturnValue({
      data: {
        company_id: "company-1",
        generated_at: "2026-10-03T12:00:00Z",
        items: [],
      },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof closeHooks.useAccountantReview>);
    renderRoute();
    expect(
      screen.getByText(
        /No review items were returned by the canonical server queue/i,
      ),
    ).toBeVisible();
    expect(
      screen.queryByText(/approved by accountant/i),
    ).not.toBeInTheDocument();
  });

  it("fails closed with operator-safe states when comparison or readiness APIs fail", () => {
    vi.mocked(closeHooks.useReportComparisons).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as unknown as ReturnType<typeof closeHooks.useReportComparisons>);
    vi.mocked(closeHooks.usePeriodCloseReadiness).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as unknown as ReturnType<typeof closeHooks.usePeriodCloseReadiness>);
    renderRoute();
    expect(
      screen.getByText(/Canonical report comparisons are unavailable/i),
    ).toBeVisible();
    expect(screen.getByText(/Close readiness is unavailable/i)).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Close period" }),
    ).not.toBeInTheDocument();
  });

  it("shows stale-readiness rejection without automatic success", () => {
    vi.mocked(closeHooks.useGovernedPeriodClose).mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      isError: true,
      isSuccess: false,
    } as unknown as ReturnType<typeof closeHooks.useGovernedPeriodClose>);
    renderRoute();
    expect(
      screen.getByText(/This reconciliation changed or is no longer ready/i),
    ).toBeVisible();
    expect(
      screen.queryByText(/server closed the period/i),
    ).not.toBeInTheDocument();
  });

  it("fails closed for unauthorized users", () => {
    permissions = new Set();
    renderRoute();
    expect(
      screen.getByText(/Accounting report permission is required/i),
    ).toBeVisible();
  });
});
