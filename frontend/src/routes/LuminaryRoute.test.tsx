import { fireEvent, render, screen } from "@testing-library/react";
import { AxiosError } from "axios";
import { MemoryRouter, useLocation } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LuminaryRoute } from "./LuminaryRoute";

const state = vi.hoisted(() => ({
  canRead: true,
  canAnalyze: true,
  error: undefined as unknown,
  refetch: vi.fn(),
  analyze: vi.fn(),
}));

vi.mock("../auth", () => ({
  useHasPermission: (permission: string) =>
    permission.endsWith("_READ") ? state.canRead : state.canAnalyze,
}));
vi.mock("../hooks/useLuminary", () => ({
  useLuminaryBriefing: () => ({
    isPending: false,
    isError: Boolean(state.error),
    error: state.error,
    data: undefined,
    refetch: state.refetch,
  }),
  useLuminarySourceReadiness: () => ({
    isPending: false,
    data: {
      profitability: {
        sources: [
          {
            source: "revenue",
            state: "AVAILABLE",
            evidence_count: 2,
            explanation: "Admitted evidence.",
          },
          {
            source: "overhead_allocation",
            state: "POLICY_REQUIRED",
            evidence_count: 0,
            explanation: "Owner policy required.",
          },
        ],
      },
    },
  }),
  useLuminaryOwnerEconomics: () => ({
    isPending: false,
    data: {
      readiness: "READY",
      confidence: { score_percent: 90 },
      job_economics: [
        {
          job_id: "job-1", job_number: "J-100", job_status: "completed",
          customer: { id: "customer-1", name: "All County Customer" },
          branch: { id: "branch-1", name: "Main" }, service_category: "drain_cleaning",
          readiness: "PARTIAL", invoiced_revenue_minor: 12550,
          settlement_applied_minor: null, accepted_worked_seconds: 3600,
          direct_wage_cost_minor: null, actual_material_cost_minor: null,
          other_direct_cost_minor: null, direct_contribution_minor: null,
          contribution_percent_basis_points: null, fully_loaded_profit_minor: null,
          missing_prerequisites: ["certified_direct_wage_cost", "actual_material_valuation"],
          confidence_percent: 70,
        },
      ],
      service_line_economics: [
        {
          service_category: "drain_cleaning", job_count: 1,
          contribution_ready_job_count: 0, invoiced_revenue_minor: 12550,
          accepted_worked_seconds: 3600, actual_material_cost_minor: null,
          direct_contribution_minor: null, average_invoiced_ticket_minor: 12550,
          readiness: "PARTIAL", missing_prerequisites: ["certified_direct_wage_cost"],
        },
      ],
      admitted_source_evidence: {
        authority: "accepted_acp_native_owning_domain_facts",
        admitted_reference_count: 7,
        evidence_digest: "b".repeat(64),
        summary: {
          job_count: 2,
          invoiced_revenue_minor: 12550,
          currency: "USD",
          accepted_worked_seconds: 3600,
          material_cost_minor: null,
          settlement_applied_minor: null,
        },
        families: {
          REVENUE: {
            state: "AVAILABLE",
            reference_count: 2,
            limitation: "Invoiced basis is not earned revenue or settlement.",
          },
        },
      },
      scenario: null,
      recommendation_candidates: [
        {
          recommendation_id: "candidate-1",
          family: "PRICING",
          owner_decision_required: "Review measured Job contribution",
          economic_mechanism: "Measured contribution is below zero; no cause is presumed.",
          confidence: 90,
          status: "CANDIDATE_READ_ONLY",
        },
      ],
      packet_digest: "a".repeat(64),
    },
  }),
  useAnalyzeLuminary: () => ({
    mutate: state.analyze,
    isPending: false,
    isError: false,
  }),
}));

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{`${location.pathname}${location.search}`}</output>;
}

const renderRoute = () =>
  render(
    <MemoryRouter>
      <LuminaryRoute />
      <LocationProbe />
    </MemoryRouter>,
  );

describe("Luminary workspace recovery", () => {
  beforeEach(() => {
    state.canRead = true;
    state.canAnalyze = true;
    state.error = undefined;
    state.refetch.mockReset();
    state.analyze.mockReset();
  });

  it("shows admitted native evidence without presenting it as profitability", () => {
    renderRoute();
    expect(screen.getByText("Admitted source evidence")).toBeVisible();
    expect(screen.getByText(/7 accepted native reference/)).toBeVisible();
    expect(screen.getByText(/Invoiced basis is not earned revenue/)).toBeVisible();
    expect(screen.getByText(/remain separate from calculated profitability/)).toBeVisible();
    expect(screen.getByText(/Invoiced revenue \$125\.50/)).toBeVisible();
    expect(screen.getByText(/Accepted worked hours 1\.00/)).toBeVisible();
    expect(screen.getByText("What ACP knows by Job")).toBeVisible();
    expect(screen.getByText("Job J-100")).toBeVisible();
    expect(screen.getByText("What it means by service line")).toBeVisible();
    expect(screen.getAllByText("$125.50").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/certified direct wage cost/).length).toBeGreaterThan(0);
  });

  it("retries a temporary briefing failure without offering analysis", () => {
    state.error = new AxiosError("unavailable");
    renderRoute();
    expect(screen.getByText(/No briefing state was inferred/i)).toBeVisible();
    expect(
      screen.queryByRole("button", { name: /Analyze accepted evidence/i }),
    ).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Retry briefing/i }));
    expect(state.refetch).toHaveBeenCalledOnce();
  });

  it("offers analysis only for a concealed not-found briefing", () => {
    state.error = new AxiosError("missing", undefined, undefined, undefined, {
      status: 404,
    } as never);
    renderRoute();
    fireEvent.click(
      screen.getByRole("button", { name: /Analyze accepted evidence/i }),
    );
    expect(state.analyze).toHaveBeenCalledOnce();
    expect(
      screen.queryByRole("button", { name: /Retry briefing/i }),
    ).toBeNull();
  });

  it("renders the deterministic source matrix and LIA handoff", () => {
    renderRoute();
    expect(
      screen.getByText("Can I trust the profitability answer?"),
    ).toBeVisible();
    expect(screen.getByText("AVAILABLE")).toBeVisible();
    expect(screen.getByText("POLICY REQUIRED")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Ask LIA about this evidence" }),
    ).toBeVisible();
    fireEvent.click(
      screen.getByRole("button", { name: "Ask LIA about this evidence" }),
    );
    expect(screen.getByTestId("location")).toHaveTextContent(
      "/lia?contextDomain=luminary",
    );
    expect(screen.getByText("Owner economics decision support")).toBeVisible();
    expect(screen.getByText("Read-only scenario")).toBeVisible();
    expect(screen.getByText("No hypothetical scenario selected.")).toBeVisible();
    expect(screen.getByText("Review measured Job contribution")).toBeVisible();
    expect(screen.getByText(/No price, Employee, Payroll, payment, or Accounting state can be changed/i)).toBeVisible();
  });
});
