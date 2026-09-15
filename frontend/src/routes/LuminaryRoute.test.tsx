import { fireEvent, render, screen } from "@testing-library/react";
import { AxiosError } from "axios";
import { MemoryRouter } from "react-router";
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
      admitted_source_evidence: {
        authority: "accepted_acp_native_owning_domain_facts",
        admitted_reference_count: 7,
        evidence_digest: "b".repeat(64),
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

const renderRoute = () =>
  render(
    <MemoryRouter>
      <LuminaryRoute />
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
    expect(screen.getByText("Owner economics decision support")).toBeVisible();
    expect(screen.getByText("Read-only scenario")).toBeVisible();
    expect(screen.getByText("No hypothetical scenario selected.")).toBeVisible();
    expect(screen.getByText("Review measured Job contribution")).toBeVisible();
    expect(screen.getByText(/No price, Employee, Payroll, payment, or Accounting state can be changed/i)).toBeVisible();
  });
});
