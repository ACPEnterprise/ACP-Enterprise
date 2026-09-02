import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as api from "../api/dataQuality";
import { DataQualityRoute } from "./DataQualityRoute";

describe("DataQualityRoute", () => {
  it("explains record blockers without exposing a correction action", async () => {
    vi.spyOn(api, "getDataQualitySummary").mockResolvedValue({
      catalog_version: "2026-09-01", catalog_digest: "a".repeat(64), company_id: "company-1",
      branch_scope: ["branch-1"], scanned_rules: 7, total_issues: 1,
      blocks_new_operation: 1, historical_only: 0, owner_review: 0, limit: 100, offset: 0,
      issues: [{ rule_id: "DQ-LOCATION-001", domain: "LOCATIONS", state: "INCOMPLETE",
        severity: "HIGH", launch_impact: "BLOCKS_SPECIFIC_RECORD", safe_record_identity: "location-1",
        explanation: "Service Location lacks complete operational address evidence.",
        missing_or_conflicting_evidence: ["complete operational address"], repair_owner: "CUSTOMERS",
        evidence_digest: "b".repeat(64), blocks_new_operation: true }],
    });
    render(<QueryClientProvider client={new QueryClient()}><DataQualityRoute/></QueryClientProvider>);
    expect(await screen.findByText("Service Location lacks complete operational address evidence.")).toBeInTheDocument();
    expect(screen.getByText("BLOCKS SPECIFIC RECORD")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /fix|merge|correct/i })).not.toBeInTheDocument();
  });
});
