import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BusinessEconomicsRoute } from "./BusinessEconomicsRoute";

let allowed = false;
let detailData: Record<string, unknown> | null = null;
vi.mock("../auth", () => ({ useHasPermission: () => allowed }));
vi.mock("../hooks/useBusinessEconomics", () => ({
  useEconomicsResult: () => ({ isPending: false, isError: false, data: detailData }),
  useEconomicsWorkspace: () => ({ isPending: false, isError: false, data: {
    period: { start: "2027-01-01", end: "2027-01-31" }, prior_period: { start: "2026-12-01", end: "2026-12-31" },
    quality_state: "partial", currency: "USD", source_result_count: 2, excluded_job_count: 0, job_count: 2, complete_job_count: 1, unclassified_job_count: 1,
    totals: { revenue: 100000, labor: 30000, materials: 20000, equipment: 0, truck: 0, overhead: 0, gross_profit: 50000, net_profit: 50000 },
    jobs: detailData ? [{ result_id: "result-1", job_id: "job-1", job_number: "JOB-000001", job_status: "completed", branch_name: "Main", customer_name: "Synthetic", service_category: "repair", currency: "USD", revenue_minor: 100000, labor_minor: 30000, materials_minor: null, other_direct_cost_minor: 0, contribution_minor: null, net_profit_minor: null, margin_basis_points: null, quality_state: "partial", confidence_percent: 0, missing_categories: ["materials"] }] : [], service_categories: [], customers: [], branches: [], fully_allocated_available: false,
    explanation: "Incomplete Jobs remain visible.", comparison: { state: "unavailable", reason: "Prior evidence is incomplete." },
    readiness: { evidence: "partial", allocation_policy: "not_configured", attribution: "partial", policy_gaps: [] }, beacon_conditions: [{ kind: "incomplete_economic_evidence", state: "partial" }],
  } }),
}));

describe("BusinessEconomicsRoute", () => {
  beforeEach(() => { allowed = false; detailData = null; });
  it("fails closed without Economics read authority", () => { render(<BusinessEconomicsRoute/>); expect(screen.getByText(/not authorized/i)).toBeVisible(); });
  it("shows truthful partial and no-policy states", () => { allowed = true; render(<BusinessEconomicsRoute/>); expect(screen.getByText(/Evidence partial/i)).toBeVisible(); expect(screen.getAllByText(/fully allocated profitability is unavailable/i).length).toBeGreaterThan(0); expect(screen.getByText("$1,000.00")).toBeVisible(); });
  it("exposes safe provenance, quality, missing evidence, and allocation authority", async () => {
    allowed = true;
    detailData = {
      id: "result-1", subject_id: "job-1", scope: "job", period_start: "2027-01-01", period_end: "2027-01-31", currency: "USD",
      components: { materials: { state: "missing", amount_minor: null, confidence_percent: 0, explanation: "Authoritative materials evidence is missing.", evidence: [] } },
      quality: { completeness_percent: 83, freshness_status: "current", missing_categories: ["materials"] },
      explanation: { answer: "Contribution is unavailable.", findings: [], limitations: [] },
      lineage: { result_digest: "result-digest", admission_digest: "admission-digest", package_digest: "package-digest", computation_digest: "computation-digest", acquisition_digests: [], allocation_digests: [], explanation_ids: [] },
    };
    render(<BusinessEconomicsRoute/>);
    await userEvent.click(screen.getByRole("button", { name: "JOB-000001" }));
    expect(await screen.findByText(/Measurement package digest/i)).toBeVisible();
    expect(screen.getByText("package-digest")).toBeVisible();
    expect(screen.getByText("83%")).toBeVisible();
    expect(screen.getByText("materials")).toBeVisible();
    expect(screen.getByText(/No accepted allocation authority/i)).toBeVisible();
  });
});
