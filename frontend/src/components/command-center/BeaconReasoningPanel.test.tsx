import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import type { ActiveBeaconRecommendation } from "../../api/beacon";
import { BeaconReasoningPanel } from "./BeaconReasoningPanel";

const recommendation: ActiveBeaconRecommendation = {
  recommendation_id: "11111111-1111-4111-8111-111111111111",
  definition_id: "evidence_gap.branch_scheduling_policy",
  definition_version: 1,
  root_issue_key: "branch-scheduling:branch-1",
  kind: "EVIDENCE_GAP",
  title: "Main Branch scheduling policy is incomplete",
  measured_fact: "Main Branch has no scheduling calendar.",
  interpretation: "Dispatch cannot evaluate capacity.",
  recommended_human_action: "Configure the Branch schedule.",
  responsibility: "OWNER",
  source_authority: "Scheduling Branch calendar authority",
  evidence_as_of: "2026-09-29T12:00:00Z",
  coverage: "One authorized Branch",
  confidence: "HIGH",
  limitations: ["No financial impact is inferred."],
  affected_capabilities: ["Scheduling", "Dispatch"],
  decisions_blocked: ["Scheduling capacity"],
  priority_window: "TODAY",
  priority_score: 80,
  priority_reason: "Owner configuration is required.",
  priority_factors: [
    {
      factor: "operational_blocker",
      available: true,
      contribution: 30,
      explanation: "Scheduling is blocked.",
    },
  ],
  improves_if_resolved: "Dispatch capacity becomes evaluable.",
  drilldown_path:
    "/administration#branch-scheduling-setup",
  action_destination: "Administration → Branch Scheduling Setup",
  evidence: [
    {
      entity_type: "branch_scheduling_calendar",
      entity_id: "11111111-1111-4111-8111-111111111111",
      digest: null,
      as_of: "2026-09-29T12:00:00Z",
    },
  ],
  related_recommendations: [],
  expires_at: "2026-09-29T12:15:00Z",
};

describe("BeaconReasoningPanel", () => {
  it("separates fact, interpretation, and human action with evidence context", () => {
    render(
      <MemoryRouter>
        <BeaconReasoningPanel
          evaluatedAt="2026-09-29T12:00:00Z"
          isError={false}
          isPending={false}
          items={[recommendation]}
          readinessAdapters={[
            {
              domain: "PAYROLL",
              state: "EVALUATED",
              source_authority: "Payroll run-member readiness authority",
              fact_count: 1,
              evaluated_at: "2026-09-29T12:00:00Z",
              limitation: null,
            },
            {
              domain: "MARKETING",
              state: "ADAPTER_GATED",
              source_authority: "Marketing connection readiness authority",
              fact_count: 0,
              evaluated_at: "2026-09-29T12:00:00Z",
              limitation: "No accepted Marketing readiness contract exists.",
            },
          ]}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText("Measured fact")).toBeInTheDocument();
    expect(screen.getByText(recommendation.measured_fact)).toBeInTheDocument();
    expect(screen.getByText("Interpretation")).toBeInTheDocument();
    expect(screen.getByText("Recommended human action")).toBeInTheDocument();
    expect(screen.getByText("Responsible role")).toBeInTheDocument();
    expect(screen.getByText("owner")).toBeInTheDocument();
    expect(screen.getByText("Evaluated · 1 active gap")).toBeInTheDocument();
    expect(screen.getByText("Adapter gated")).toBeInTheDocument();
    expect(
      screen.getByText("No accepted Marketing readiness contract exists."),
    ).toBeInTheDocument();
    expect(screen.getByText(/Coverage: One authorized Branch/)).toBeInTheDocument();
    expect(screen.getByText(/Scheduling capacity/)).toBeInTheDocument();
    expect(screen.getByText(/Scheduling, Dispatch/)).toBeInTheDocument();
    expect(screen.getByText(/operational blocker/i)).toBeInTheDocument();
    expect(screen.getByText("Scheduling is blocked.").closest("li")).toHaveTextContent(
      "+30",
    );
    expect(
      screen.getByRole("link", {
        name: "Administration → Branch Scheduling Setup",
      }),
    ).toHaveAttribute("href", recommendation.drilldown_path);
  });

  it("does not infer that an empty recommendation response means all sources are complete", () => {
    render(
      <MemoryRouter>
        <BeaconReasoningPanel
          isError={false}
          isPending={false}
          items={[]}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText(/does not mean every source is complete/i)).toBeInTheDocument();
  });

  it("fails closed when canonical evidence cannot be evaluated", () => {
    render(
      <MemoryRouter>
        <BeaconReasoningPanel isError isPending={false} items={undefined} />
      </MemoryRouter>,
    );

    expect(screen.getByText(/No recommendation state is inferred/i)).toBeInTheDocument();
  });
});
