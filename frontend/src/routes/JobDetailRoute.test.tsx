import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { useJob } from "../hooks/useJobs";
import type { JobDetail } from "../types/jobs";
import { JobDetailRoute } from "./JobDetailRoute";

vi.mock("../auth", () => ({ useAuth: () => ({ activeCompany: { branches: [{ id: "branch-1", name: "Main Branch", code: "MAIN" }] } }) }));
vi.mock("../hooks/useJobs");
vi.mock("../components/jobs/LifecycleActionButtons", () => ({ LifecycleActionButtons: () => <div>Lifecycle controls</div> }));
vi.mock("../components/jobs/JobCompletionStatus", () => ({ JobCompletionStatus: () => <div>Completion status</div> }));
vi.mock("../components/jobs/JobOperationalTimeline", () => ({ JobOperationalTimeline: () => <div>Operational timeline</div> }));

const job = { id: "job-1", job_number: "JOB-000001", branch_id: "branch-1", status: "ready", priority: "high", concurrency_version: 2, job_type_code: "repair", customer_reported_problem: "No heat", internal_description: "Inspect furnace", created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-02T00:00:00Z", activated_at: "2026-01-02T00:00:00Z", started_at: null, paused_at: null, pause_reason_code: null, completed_at: null, completed_by_user_id: null, cancelled_at: null, cancelled_by_user_id: null, cancellation_reason_code: null, customer: { id: "customer-1", customer_number: "CUS-1", display_name: "Taylor Home" }, service_location: { id: "location-1", nickname: "Home", address_line_1: "10 Main", address_line_2: null, city: "Albany", state: "NY", postal_code: "12207", country: "US" }, appointments: [] } as unknown as JobDetail;
function renderRoute() { const client = new QueryClient(); return render(<MemoryRouter initialEntries={["/jobs/job-1"]}><QueryClientProvider client={client}><Routes><Route path="/jobs/:jobId" element={<JobDetailRoute />} /></Routes></QueryClientProvider></MemoryRouter>); }

describe("JobDetailRoute", () => {
  it("renders loading and complete operational detail states", () => {
    vi.mocked(useJob).mockReturnValueOnce({ isLoading: true } as never); const view = renderRoute(); expect(screen.getByRole("status", { name: "Loading Jobs" })).toBeInTheDocument();
    vi.mocked(useJob).mockReturnValue({ isLoading: false, isError: false, data: job } as never); view.unmount(); renderRoute();
    expect(screen.getByRole("heading", { name: "JOB-000001" })).toBeInTheDocument(); expect(screen.getByText("Taylor Home")).toBeInTheDocument(); expect(screen.getByText("Main Branch (MAIN)")).toBeInTheDocument();
  });
  it("renders a concealed not-found response without retry", () => {
    vi.mocked(useJob).mockReturnValue({ isLoading: false, isError: true, error: { isAxiosError: true, response: { status: 404 } }, refetch: vi.fn() } as never); renderRoute();
    expect(screen.getByText("Job not found")).toBeInTheDocument(); expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });
});
