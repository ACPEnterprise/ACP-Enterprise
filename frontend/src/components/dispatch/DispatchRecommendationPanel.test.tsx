import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useDispatchRecommendation } from "../../hooks/useDispatch";
import type { DispatchBoardItem } from "../../types/dispatch";
import { DispatchRecommendationPanel } from "./DispatchRecommendationPanel";

vi.mock("../../hooks/useDispatch", () => ({ useDispatchRecommendation: vi.fn() }));

const item: DispatchBoardItem = {
  appointment_id: "appointment-1",
  appointment_number: "APT-1",
  job_id: "job-1",
  branch_id: "branch-1",
  status: "scheduled",
  window_start_at: "2027-03-01T14:00:00Z",
  window_end_at: "2027-03-01T15:00:00Z",
  assignment: null,
};

describe("DispatchRecommendationPanel", () => {
  it("renders a proposal, explanation, limitations, and human authority boundary", () => {
    vi.mocked(useDispatchRecommendation).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        recommendation_id: "recommendation-1",
        contract_version: "dispatch.recommendation.v1",
        engine_version: "dispatch-deterministic-1",
        job_id: "job-1",
        company_id: "company-1",
        branch_id: "branch-1",
        candidates: [{
          employee_id: "employee-1",
          proposed_window: { start_at: item.window_start_at, end_at: item.window_end_at },
          placement_class: "BEST_OVERALL_FIT",
          eligible: true,
          rank: 1,
          constraints: [{ constraint: "customer_window", result: "PASS", explanation: "Customer window is preserved." }],
          tradeoffs: ["Travel duration is unavailable and is not estimated."],
          limitations: [],
          confidence: "UNKNOWN",
        }],
        risk_conditions: [],
        recovery_options: [],
        evidence: [],
        limitations: ["Travel remains external-gated."],
        recommendation_digest: "a".repeat(64),
        mutation_authority: "none",
      },
    } as ReturnType<typeof useDispatchRecommendation>);
    render(<DispatchRecommendationPanel item={item} />);
    expect(screen.getByText(/Proposed placement · no schedule change/i)).toBeVisible();
    expect(screen.getByRole("heading", { name: "Why?" })).toBeVisible();
    expect(screen.getByText(/Customer window is preserved/)).toBeVisible();
    expect(screen.getByText(/Dispatcher approval is required/)).toBeVisible();
  });

  it("fails safely when Job authority is absent", () => {
    render(<DispatchRecommendationPanel item={{ ...item, job_id: null }} />);
    expect(screen.getByText(/Job authority is missing/)).toBeVisible();
  });
});
