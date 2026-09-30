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
    } as never);
  });

  it("keeps Job activity separate from paid workday and records Parts Run", async () => {
    render(<MemoryRouter initialEntries={["/technician/jobs/job-1"]}><Routes><Route path="/technician/jobs/:jobId" element={<TechnicianJobRoute />} /></Routes></MemoryRouter>);
    expect(screen.getByText(/does not clock you in or out/i)).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Parts Run" }));
    expect(mutate).toHaveBeenCalledWith({ action: "change", activity: "parts_run", jobVersion: 3, appointmentVersion: 2 });
  });
});
