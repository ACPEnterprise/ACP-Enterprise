import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BusinessEconomicsRoute } from "./BusinessEconomicsRoute";

let allowed = false;
let workspaceEnabled: boolean | undefined;
let detailEnabled: boolean | undefined;
let workspaceMode: "success" | "error" | "pending" = "success";
const refetch = vi.fn();
vi.mock("../auth", () => ({ useHasPermission: () => allowed }));
vi.mock("../hooks/useBusinessEconomics", () => ({
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
    if (workspaceMode === "pending") return { isPending: true, isError: false, data: null, refetch };
    if (workspaceMode === "error") return { isPending: false, isError: true, data: null, refetch };
    return { isPending: false, isError: false, refetch, data: {
    period: { start: "2027-01-01", end: "2027-01-31" }, prior_period: { start: "2026-12-01", end: "2026-12-31" },
    quality_state: "partial", currency: "USD", source_result_count: 2, excluded_job_count: 0, job_count: 2, complete_job_count: 1, unclassified_job_count: 1,
    totals: { revenue: 100000, labor: 30000, materials: 20000, equipment: 0, truck: 0, overhead: 0, gross_profit: 50000, net_profit: 50000 },
    jobs: [], service_categories: [], customers: [], branches: [], fully_allocated_available: false,
    explanation: "Incomplete Jobs remain visible.", comparison: { state: "unavailable", reason: "Prior evidence is incomplete." },
    readiness: { evidence: "partial", allocation_policy: "policy_required", attribution: "partial", allocation_authority: { state: "policy_required", pool_policy: "unconfigured", basis_policy: "unconfigured", source_evidence: "insufficient_source", supported_basis_types: ["labor_hours", "revenue"], owner_decision: "Select approved cost pools, source evidence, and an allocation basis; no default is applied.", callback_economics: "external_gate" }, policy_gaps: [] }, beacon_conditions: [{ kind: "incomplete_economic_evidence", state: "partial" }],
    } };
  },
}));

describe("BusinessEconomicsRoute", () => {
  beforeEach(() => { allowed = false; workspaceMode = "success"; workspaceEnabled = undefined; detailEnabled = undefined; refetch.mockReset(); });
  it("fails closed without Economics read authority or issuing the query", () => { render(<BusinessEconomicsRoute/>); expect(screen.getByText(/not authorized/i)).toBeVisible(); expect(workspaceEnabled).toBe(false); expect(detailEnabled).toBe(false); });
  it("shows truthful partial, no-policy, and expanded owner-question states", () => { allowed = true; render(<BusinessEconomicsRoute/>); expect(screen.getByText(/Evidence partial/i)).toBeVisible(); expect(screen.getAllByText(/fully allocated profitability is unavailable/i).length).toBeGreaterThan(0); expect(screen.getByText(/no default is applied/i)).toBeVisible(); expect(screen.getByRole("option", { name: /what prevents full profitability/i })).toBeVisible(); expect(screen.getByRole("option", { name: /what should i inspect first/i })).toBeVisible(); expect(screen.getByText("$1,000.00")).toBeVisible(); });
  it("offers a safe retry when Economics is temporarily unavailable", async () => { allowed = true; workspaceMode = "error"; render(<BusinessEconomicsRoute/>); expect(screen.getByText(/no value was inferred/i)).toBeVisible(); await userEvent.click(screen.getByRole("button", { name: /retry economics/i })); expect(refetch).toHaveBeenCalledOnce(); });
});
