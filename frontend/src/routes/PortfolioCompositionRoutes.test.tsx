import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import * as auditApi from "../api/audit";
import { AuditRoute } from "./AuditRoute";
import { OperatorGuideRoute } from "./OperatorGuideRoute";
import { ReportCenterRoute } from "./ReportCenterRoute";

describe("portfolio composition routes", () => {
  it("renders safe audit evidence without dumping detail payloads", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    vi.spyOn(auditApi, "listAuditRecords").mockResolvedValue([{ id: "audit-1", action: "job.completed", outcome: "success", actor_user_id: null, company_id: "company-1", branch_id: null, resource_type: "job", resource_id: "job-1", reason_code: null, correlation_id: "correlation-1", details: { protected_payload: "must-not-render" }, occurred_at: "2026-08-30T12:00:00Z" }]);
    render(<QueryClientProvider client={client}><AuditRoute /></QueryClientProvider>);
    expect(await screen.findByText("job.completed")).toBeInTheDocument();
    expect(screen.getByText(/Correlation correlation-1/)).toBeInTheDocument();
    expect(screen.queryByText("must-not-render")).not.toBeInTheDocument();
  });
  it("navigates authoritative reports without creating report truth", () => {
    render(<MemoryRouter><ReportCenterRoute /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Report Center" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Jobs/ })).toHaveAttribute("href", "/jobs");
    expect(screen.getByRole("link", { name: /Financial reports/ })).toHaveAttribute("href", "/financial-reports");
    expect(screen.getByText(/without creating a second analytics/i)).toBeInTheDocument();
  });

  it("explains every authoritative recovery classification deterministically", () => {
    render(<OperatorGuideRoute />);
    for (const label of ["RETRY SAFE", "RETRY AFTER REFRESH", "USER CORRECTION REQUIRED", "OWNER ADMIN ACTION REQUIRED", "RECONCILIATION REQUIRED", "TEMPORARILY UNAVAILABLE", "TERMINAL FAILURE"]) {
      expect(screen.getByRole("heading", { name: new RegExp(label) })).toBeInTheDocument();
    }
  });
});
