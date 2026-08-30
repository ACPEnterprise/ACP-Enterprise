import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useCustomerDetail } from "../hooks/useCustomers";
import { useCreateJobFromAppointment, useJobForAppointment } from "../hooks/useJobs";
import { useAppointment } from "../hooks/useScheduling";
import type { AppointmentDetail } from "../types/scheduling";
import { AppointmentDetailRoute } from "./AppointmentDetailRoute";

vi.mock("../auth", () => ({ useAuth: () => ({ activeCompany: { branches: [{ id: "branch-1", name: "Main Branch", code: "MAIN" }] } }), useHasPermission: () => false }));
vi.mock("../hooks/useCustomers");
vi.mock("../hooks/useJobs");
vi.mock("../hooks/useScheduling");

const appointment = { id: "appointment-1", appointment_number: "APT-000001", branch_id: "branch-1", customer_id: "customer-1", service_location_id: "location-1", status: "scheduled", arrival_window_start_at: "2026-07-24T13:00:00Z", arrival_window_end_at: "2026-07-24T15:00:00Z", expected_duration_minutes: 90 } as AppointmentDetail;

function renderRoute() {
  return render(<MemoryRouter initialEntries={["/appointments/appointment-1"]}><Routes><Route path="/appointments/:appointmentId" element={<AppointmentDetailRoute />} /></Routes></MemoryRouter>);
}

describe("AppointmentDetailRoute", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAppointment).mockReturnValue({ isLoading: false, isError: false, data: appointment } as never);
    vi.mocked(useCreateJobFromAppointment).mockReturnValue({ mutate: vi.fn(), isPending: false, error: null } as never);
    vi.mocked(useCustomerDetail).mockReturnValue({ data: { first_name: "Alex", last_name: "Taylor", business_name: null, properties: [{ id: "location-1", address_line_1: "10 Main Street", address_line_2: null, city: "Albany", state: "NY", postal_code: "12207" }] } } as never);
  });
  it("shows the authoritative related Job and navigates by business number", () => {
    vi.mocked(useJobForAppointment).mockReturnValue({ isLoading: false, isError: false, data: { items: [{ id: "job-1", job_number: "JOB-000001", status: "ready" }] } } as never);
    renderRoute();
    expect(screen.getByRole("heading", { name: "APT-000001" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "JOB-000001" })).toHaveAttribute("href", "/jobs/job-1");
    expect(screen.queryByRole("button", { name: "Create Job" })).not.toBeInTheDocument();
  });
  it("offers creation for an eligible unlinked Appointment", async () => {
    vi.mocked(useJobForAppointment).mockReturnValue({ isLoading: false, isError: false, data: { items: [] } } as never);
    renderRoute();
    expect(screen.getByText("No Job has been created from this Appointment.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Create Job" }));
    expect(screen.getByRole("heading", { name: "Create Job from APT-000001" })).toBeInTheDocument();
  });
  it("keeps Appointment rendering intact when Job relationship access is denied", () => {
    vi.mocked(useJobForAppointment).mockReturnValue({ isLoading: false, isError: true, error: new Error("denied") } as never);
    renderRoute();
    expect(screen.getByRole("heading", { name: "APT-000001" })).toBeInTheDocument();
    expect(screen.getByText("Related Job information is unavailable with your current access.")).toBeInTheDocument();
  });
});
