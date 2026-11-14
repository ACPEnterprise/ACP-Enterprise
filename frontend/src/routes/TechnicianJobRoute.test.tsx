import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useTechnicianField } from "../hooks/useTechnicianField";
import { TechnicianJobRoute } from "./TechnicianJobRoute";

vi.mock("../hooks/useTechnicianField", () => ({ useTechnicianField: vi.fn() }));

const mutate = vi.fn();
const state = {
  job_id: "job-1", assignment_id: "assignment-1", appointment_id: "appointment-1",
  job_number: "JOB-000001", job_status: "in_progress", job_type_code: "repair", priority: "normal",
  customer_display_name: "Jamie Customer", contact_display_name: "Jamie Customer",
  contact_phone: "555-0100", contact_email: "jamie@example.com",
  service_location_label: "12 Main St, Towson, MD 21204",
  customer_reported_problem: "Leaking fixture", internal_description: "Inspect and repair",
  window_start_at: "2026-11-14T14:00:00Z", window_end_at: "2026-11-14T16:00:00Z",
  job_version: 3, appointment_version: 2, active_activity: "working" as const,
  visit_finished: false, work_summary_recorded: false, customer_disposition: null,
  completion_ready: false, requirement_snapshot_version: null,
  missing_requirements: ["work_performed_summary"], commercial_authorization: "missing" as const,
  non_billable_reason: null, invoice_handoff_status: null, invoice_id: null,
};

describe("Technician Job activity", () => {
  beforeEach(() => {
    mutate.mockReset();
    vi.mocked(useTechnicianField).mockReturnValue({
      state: { data: state, isLoading: false, isError: false },
      activity: { mutate, isError: false }, continuation: { mutate: vi.fn(), isError: false },
      lifecycle: { mutate: vi.fn(), isError: false },
      note: { mutate: vi.fn(), isPending: false, isError: false },
    } as never);
  });

  it("keeps Job activity separate from paid workday and records Parts Run", async () => {
    render(<MemoryRouter initialEntries={["/technician/jobs/job-1"]}><Routes><Route path="/technician/jobs/:jobId" element={<TechnicianJobRoute />} /></Routes></MemoryRouter>);
    expect(screen.getByText(/does not clock you in or out/i)).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Parts Run" }));
    expect(mutate).toHaveBeenCalledWith({ action: "change", activity: "parts_run", jobVersion: 3, appointmentVersion: 2 });
  });

  it("keeps assigned customer and Job context usable at mobile scale", () => {
    render(<MemoryRouter initialEntries={["/technician/jobs/job-1"]}><Routes><Route path="/technician/jobs/:jobId" element={<TechnicianJobRoute />} /></Routes></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Jamie Customer" })).toBeVisible();
    expect(screen.getByText("12 Main St, Towson, MD 21204")).toBeVisible();
    expect(screen.getByRole("link", { name: "Call customer" })).toHaveAttribute("href", "tel:555-0100");
    expect(screen.getByText("Leaking fixture")).toBeVisible();
    expect(screen.getByLabelText("Work performed")).toBeVisible();
  });
});
