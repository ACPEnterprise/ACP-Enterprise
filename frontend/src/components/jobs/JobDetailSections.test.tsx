import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import type { JobDetail } from "../../types/jobs";
import { AppointmentSummaryTable } from "./JobDetailSections";

describe("AppointmentSummaryTable", () => {
  it("links authoritative Appointment summaries by business number", () => {
    const job = { appointments: [{ appointment_id: "appointment-1", visit_sequence: 1, appointment_number: "APT-000001", status: "scheduled", arrival_window_start_at: "2026-07-24T13:00:00Z", arrival_window_end_at: "2026-07-24T15:00:00Z", expected_duration_minutes: 90 }] } as unknown as JobDetail;
    render(<MemoryRouter><AppointmentSummaryTable job={job} /></MemoryRouter>);
    expect(screen.getByRole("link", { name: "APT-000001" })).toHaveAttribute("href", "/appointments/appointment-1");
    expect(screen.getByText("scheduled")).toBeInTheDocument();
  });
  it("does not infer an Appointment when no authoritative link exists", () => {
    render(<MemoryRouter><AppointmentSummaryTable job={{ appointments: [] } as unknown as JobDetail} /></MemoryRouter>);
    expect(screen.getByText("No Appointments linked.")).toBeInTheDocument();
  });
});
