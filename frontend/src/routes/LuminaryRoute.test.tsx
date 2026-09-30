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
  emptyServices: false,
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
      period: { start: "2026-09-01", end: "2026-09-15" },
      prior_period: { start: "2026-08-17", end: "2026-08-31" },
      generated_at: "2026-09-16T12:00:00Z",
      readiness: "READY",
      confidence: { score_percent: 90 },
      currency: "USD",
      owner_health: {
        revenue_production: {
          value_minor: 12550, classification: "AUTHORITATIVE",
          basis: "invoiced_revenue", currency: "USD",
          limitation: "Accepted invoiced revenue is not earned revenue.",
        },
        economic_contribution: {
          value_minor: null, classification: "UNAVAILABLE", currency: "USD",
          formula: "revenue minus admitted job-variable costs",
          limitation: "Complete admitted direct costs are required.",
        },
        required_economic_burden: {
          value_minor: null, classification: "UNAVAILABLE", currency: "USD",
          missing_components: ["owner_compensation", "trucks_and_fixed_costs"],
          policy_state: "policy_required",
          limitation: "A complete approved burden pool is required.",
        },
        economic_health: {
          value_basis_points: null, classification: "UNAVAILABLE",
          break_even_basis_points: 10000, status: "UNAVAILABLE",
          formula: "economic contribution divided by required economic burden",
          limitation: "Economic Health remains unknown until contribution and burden are authoritative.",
        },
        cash_health: {
          classification: "UNAVAILABLE", separate_from_economic_health: true,
          limitation: "Cash Health is a separate Accounting authority and is not inferred here.",
        },
      },
      active_reasoning: {
        contribution: {
          state: "PARTIAL", value_minor: null,
          job_population_coverage_basis_points: 0,
          coverage_basis: "jobs_with_complete_admitted_variable_costs",
          ready_job_count: 0, job_count: 1,
        },
        required_burden: {
          state: "UNAVAILABLE", value_minor: null, coverage_basis_points: null,
          coverage_limitation: "Category coverage is not converted to a percentage without category-level authoritative values.",
        },
        economic_health: { state: "UNAVAILABLE", status: "UNAVAILABLE", value_basis_points: null },
        can_conclude: ["Revenue Production at its explicitly labeled authority and basis."],
        cannot_conclude: ["ACP cannot state whether the business is above or below break-even."],
        ranked_evidence_gaps: [{
          rank: 1, gap: "certified_direct_wage_cost", evidence_state: "UNAVAILABLE",
          decision_impact: "BLOCKS_CONTRIBUTION_AND_HEALTH", priority_tier: 1,
          affected_job_count: 1, affected_authoritative_revenue_minor: 12550,
          affected_calculations: ["ECONOMIC_CONTRIBUTION", "ECONOMIC_HEALTH"],
          expected_source: "Payroll / Business Economics", responsible_party: "OWNER",
          ui_path: "/payroll", ui_path_label: "Payroll -> First real Payroll readiness",
          why_it_matters: "Economic Contribution cannot subtract authoritative Job-variable labor cost.",
          unlocks: "direct labor cost and Job Economic Contribution",
          evidence_freshness: "partial", normal_workflow_available: true,
          owner_decision_dependency: true,
        }],
        highest_value_next_action: {
          rank: 1, gap: "certified_direct_wage_cost", evidence_state: "UNAVAILABLE",
          decision_impact: "BLOCKS_CONTRIBUTION_AND_HEALTH", priority_tier: 1,
          affected_job_count: 1, affected_authoritative_revenue_minor: 12550,
          affected_calculations: ["ECONOMIC_CONTRIBUTION", "ECONOMIC_HEALTH"],
          expected_source: "Payroll / Business Economics", responsible_party: "OWNER",
          ui_path: "/payroll", ui_path_label: "Payroll -> First real Payroll readiness",
          why_it_matters: "Economic Contribution cannot subtract authoritative Job-variable labor cost.",
          unlocks: "direct labor cost and Job Economic Contribution",
          evidence_freshness: "partial", normal_workflow_available: true,
          owner_decision_dependency: true,
        },
        ranking_basis: "Decision dependency first, then affected authoritative Job population; missing values are never estimated.",
        causality_semantics: {},
      },
      economic_completion_planner: {
        contract_version: "luminary.economic-completion-planner.v1",
        read_only: true,
        period: { start: "2026-09-01", end: "2026-09-15" },
        summary: {
          complete_category_count: 3,
          partial_category_count: 1,
          missing_category_count: 8,
          unavailable_category_count: 0,
          total_category_count: 12,
        },
        categories: [],
        ranked_completion_plan: [{
          category: "FIELD_LABOR_AND_PAYROLL_BURDEN",
          label: "Field labor and Payroll burden",
          economic_role: "VARIABLE_COST_AND_REQUIRED_BURDEN",
          dependencies: ["certified_direct_wage_cost", "field_capacity_burden"],
          sources: ["Payroll", "Timekeeping", "Workforce"],
          responsible_parties: ["OWNER", "ACCOUNTANT", "SYSTEM"],
          ui_path: "/payroll",
          ui_path_label: "Payroll -> First real Payroll readiness",
          blocked_calculations: ["ECONOMIC_CONTRIBUTION", "REQUIRED_ECONOMIC_BURDEN", "ECONOMIC_HEALTH"],
          blocked_decisions: ["JOB_PROFITABILITY_CONFIDENCE", "BREAK_EVEN_EVALUATION"],
          unlocks: ["authoritative Job-variable labor cost", "stronger break-even authority"],
          priority_tier: 1,
          rank: 1,
          state: "PARTIAL",
          state_reason: null,
          missing_dependencies: ["field_capacity_burden"],
          affected_job_count: 1,
          affected_authoritative_revenue_minor: 12550,
          evidence_freshness: "partial",
          normal_workflow_available: true,
          owner_confirmed: {
            supported: false,
            reason: "No canonical owner-confirmed value authority.",
            effective_period: { start: "2026-09-01", end: "2026-09-15" },
            supersession_behavior: "UNAVAILABLE_UNTIL_CANONICAL_AUTHORITY_EXISTS",
          },
        }],
        highest_value_next_completion: null,
        ranking_basis: ["business decisions blocked"],
        ranking_limit: "No missing dollar value or industry estimate is used.",
        owner_confirmed_authority: {
          found: false,
          reason: "No canonical owner-confirmed value authority exists.",
          required_future_contract: "An owning-domain authority is required.",
        },
        decision_unlock_graph: {
          category_nodes: [], calculation_nodes: [], decision_nodes: [], edges: [],
        },
      },
      driver_analysis: {
        state: "AVAILABLE",
        observed_changes: [
          {
            metric: "revenue_production", classification: "OBSERVED_CHANGE",
            current: 12550, prior: 10050, change: 2500,
            change_basis_points_of_prior: 2487, unit: "minor_currency", currency: "USD",
          },
          {
            metric: "job_count", classification: "OBSERVED_CHANGE",
            current: 2, prior: 1, change: 1,
            change_basis_points_of_prior: 10000, unit: "count", currency: null,
          },
        ],
        measured_drivers: [{
          component: "revenue_production", classification: "MEASURED_DRIVER",
          contribution_effect_minor: 2500,
          materiality_basis: "absolute_arithmetic_contribution_effect",
          causality: "UNPROVEN",
        }],
        possible_drivers: [{
          driver: "job_mix", classification: "POSSIBLE_DRIVER",
          reason: "Job count changed; service-mix evidence must be inspected before attributing cause.",
        }],
        unproven_causes: [{
          cause: "why_measured_components_changed", classification: "UNPROVEN_CAUSE",
          reason: "Arithmetic period movement does not establish operational causation.",
        }],
        unknown_components: ["certified_direct_wage_cost"],
        economic_health: { value_basis_points: null, distance_from_break_even_basis_points: null },
        cash_health: {
          state: "SEPARATE_AUTHORITY", ar_and_collections_included: false,
          reason: "AR and collections belong to Cash Health and are not used to explain Economic Health.",
        },
      },
      facts: [
        {
          family: "REVENUE", metric: "invoiced_revenue", value: 12550,
          units: "minor_currency", currency: "USD",
          authority: "accepted_native_invoiced_or_valued_fact",
          prerequisite_completeness: "AVAILABLE",
          as_of: "2026-09-16T12:00:00Z",
        },
      ],
      trend_support: {
        state: "READY",
        authority: "equal_length_single_authority_periods_only",
        mixed_authority_periods: "labeled_and_not_combined",
        comparison: {
          state: "AVAILABLE", basis: "ACP_NATIVE_INVOICED",
          invoiced_revenue_change_minor: 2500,
        },
      },
      delta_explanation: {
        state: "PARTIAL",
        authority: "accepted_native_invoiced_evidence",
        classification: "MEASURED_PERIOD_DIFFERENCE",
        headline: "Invoiced revenue increased by 2500 minor currency units.",
        explanation: "ACP can measure invoiced revenue change but cannot explain contribution change without admitted direct costs.",
        period: { start: "2026-09-01", end: "2026-09-15" },
        prior_period: { start: "2026-08-17", end: "2026-08-31" },
        scope: { company_id: "company-1", branch_id: "branch-1" },
        as_of: "2026-09-16T12:00:00Z",
        freshness: "partial",
        currency: "USD",
        causality_boundary: "Arithmetic decomposition identifies measured contributors, not operational cause.",
        components: [{
          component: "invoiced_revenue", change_minor: 2500,
          contribution_effect_minor: null,
          classification: "MEASURED_PERIOD_DIFFERENCE",
          authority: "accepted_native_invoiced_evidence",
        }],
        unexplained_change_minor: null,
        missing_evidence: ["admitted_direct_contribution"],
      },
      evidence_priority_queue: [
        {
          prerequisite: "certified_direct_wage_cost",
          affected_job_count: 1,
          responsible_domain: "Payroll/Economics policy",
          next_safe_step: "owner_input_required",
          economic_unlock: "direct_contribution",
        },
      ],
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
      service_line_economics: state.emptyServices ? [] : [
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
    state.emptyServices = false;
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

  it("rejects a reversed period before requesting a misleading comparison", () => {
    renderRoute();
    fireEvent.change(screen.getByLabelText("Start date"), {
      target: { value: "2026-09-20" },
    });
    fireEvent.change(screen.getByLabelText("End date"), {
      target: { value: "2026-09-10" },
    });
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Choose a start date on or before the end date",
    );
  });

  it("explains an empty service-line result without inventing categories", () => {
    state.emptyServices = true;
    renderRoute();
    expect(
      screen.getByText(/No authoritative service-category evidence exists for this period/i),
    ).toBeVisible();
    expect(screen.getByText(/did not infer categories from Job descriptions/i)).toBeVisible();
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
    expect(screen.getAllByText("AVAILABLE").length).toBeGreaterThan(0);
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
    expect(screen.getByText("Where the business stands")).toBeVisible();
    expect(screen.getByText("Revenue production")).toBeVisible();
    expect(screen.getByText("Economic health")).toBeVisible();
    expect(screen.getByText("What this evidence means")).toBeVisible();
    expect(screen.getByText("Complete the economics model")).toBeVisible();
    expect(screen.getByText("Complete next")).toBeVisible();
    expect(screen.getByText("Field labor and Payroll burden")).toBeVisible();
    expect(screen.getByText(/Temporary owner-confirmed amounts are not supported/)).toBeVisible();
    expect(screen.getByText(/No missing dollar value or industry estimate/)).toBeInTheDocument();
    expect(screen.getByText("Highest-value missing evidence")).toBeVisible();
    expect(screen.getAllByRole("link", { name: "Payroll -> First real Payroll readiness" })[0]).toHaveAttribute("href", "/payroll");
    expect(screen.getByText(/covers 0 of 1 admitted Jobs/)).toBeVisible();
    expect(screen.getByText("What happened and what drove it")).toBeVisible();
    expect(screen.getAllByText("+$25.00").length).toBeGreaterThan(0);
    expect(screen.getByText(/cause unproven/)).toBeVisible();
    expect(screen.getByText(/AR and collections belong to Cash Health/)).toBeVisible();
    expect(screen.getByText(/owner compensation · trucks and fixed costs/)).toBeInTheDocument();
    expect(screen.getByText(/Cash Health is a separate Accounting authority/)).toBeInTheDocument();
    expect(screen.getByText("What changed from the prior equal period")).toBeVisible();
    expect(screen.getAllByText("+$25.00").length).toBeGreaterThan(0);
    expect(screen.getByText("Why the measured economics changed")).toBeVisible();
    expect(screen.getByText(/cannot explain contribution change/)).toBeVisible();
    expect(screen.getByText(/not operational cause/)).toBeVisible();
    expect(screen.getByText(/ACP cannot yet explain: admitted direct contribution/)).toBeVisible();
    expect(screen.getByText("Measurement freshness and authority")).toBeVisible();
    expect(screen.getByText("What evidence would improve this answer?")).toBeVisible();
    expect(screen.getByText(/responsible domain: Payroll\/Economics policy/)).toBeVisible();
    expect(screen.getByText("Read-only scenario")).toBeVisible();
    expect(screen.getByText("No hypothetical scenario selected.")).toBeVisible();
    expect(screen.getByText("Review measured Job contribution")).toBeVisible();
    expect(screen.getByText(/No price, Employee, Payroll, payment, or Accounting state can be changed/i)).toBeVisible();
  });

  it("offers day, week, month, and year owner periods", () => {
    renderRoute();
    expect(screen.getByRole("button", { name: "Today" })).toBeVisible();
    expect(screen.getByRole("button", { name: "This week" })).toBeVisible();
    expect(screen.getByRole("button", { name: "This month" })).toBeVisible();
    expect(screen.getByRole("button", { name: "This year" })).toBeVisible();
  });

  it("does not submit an invented numeric change for evidence-gated scenarios", () => {
    renderRoute();
    fireEvent.change(screen.getByLabelText("Assumption"), {
      target: { value: "ADD_TRUCK" },
    });
    expect(screen.getByLabelText("Change (basis points)")).toBeDisabled();
    expect(screen.getByText(/scenario is evidence-gated/i)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Evaluate scenario" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
