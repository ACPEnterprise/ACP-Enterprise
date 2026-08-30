import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BusinessEconomicsRoute } from "./BusinessEconomicsRoute";

let allowed = false;
vi.mock("../auth", () => ({ useHasPermission: () => allowed }));
vi.mock("../hooks/useBusinessEconomics", () => ({
  useEconomicsResult: () => ({ isPending: false, isError: false, data: null }),
  useEconomicsWorkspace: () => ({ isPending: false, isError: false, data: {
    period: { start: "2027-01-01", end: "2027-01-31" }, prior_period: { start: "2026-12-01", end: "2026-12-31" },
    quality_state: "partial", currency: "USD", source_result_count: 2, excluded_job_count: 0, job_count: 2, complete_job_count: 1, unclassified_job_count: 1,
    totals: { revenue: 100000, labor: 30000, materials: 20000, equipment: 0, truck: 0, overhead: 0, gross_profit: 50000, net_profit: 50000 },
    jobs: [], service_categories: [], customers: [], branches: [], fully_allocated_available: false,
    explanation: "Incomplete Jobs remain visible.", comparison: { state: "unavailable", reason: "Prior evidence is incomplete." },
    readiness: { evidence: "partial", allocation_policy: "not_configured", attribution: "partial", policy_gaps: [] }, beacon_conditions: [{ kind: "incomplete_economic_evidence", state: "partial" }],
  } }),
}));

describe("BusinessEconomicsRoute", () => {
  beforeEach(() => { allowed = false; });
  it("fails closed without Economics read authority", () => { render(<BusinessEconomicsRoute/>); expect(screen.getByText(/not authorized/i)).toBeVisible(); });
  it("shows truthful partial and no-policy states", () => { allowed = true; render(<BusinessEconomicsRoute/>); expect(screen.getByText(/Evidence partial/i)).toBeVisible(); expect(screen.getAllByText(/fully allocated profitability is unavailable/i).length).toBeGreaterThan(0); expect(screen.getByText("$1,000.00")).toBeVisible(); });
});
