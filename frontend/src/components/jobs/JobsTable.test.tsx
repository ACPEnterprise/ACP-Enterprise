import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { JobsTable } from "./JobsTable";

describe("JobsTable", () => {
  it("renders real transport data and navigates to detail", () => {
    render(<MemoryRouter><JobsTable jobs={[{ id: "job-1", job_number: "JOB-000001", branch_id: "branch-1", customer_id: "customer-1", customer_display_name: "Taylor Home", service_location_id: "location-1", service_location_label: "Home, Albany, NY, 12207", status: "ready", priority: "high", job_type_code: "repair", customer_reported_problem_summary: "No heat", appointment_count: 0, earliest_appointment_start_at: null, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-02T00:00:00Z", started_at: null, completed_at: null, concurrency_version: 2 }]} /></MemoryRouter>);
    expect(screen.getByRole("link", { name: "JOB-000001" })).toHaveAttribute("href", "/jobs/job-1");
    expect(screen.getByText("Taylor Home")).toBeInTheDocument(); expect(screen.getByText("ready")).toBeInTheDocument();
  });
});
