import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAppointments } from "../hooks/useScheduling";
import { SchedulingRoute } from "./SchedulingRoute";

let permissions = new Set(["COMPANY_SCHEDULING_READ"]);
vi.mock("../auth", () => ({ useAuth: () => ({ activeCompany: { branches: [{ id: "branch-1", name: "Main Branch" }] } }), useHasPermission: (code: string) => permissions.has(code) }));
vi.mock("../hooks/useScheduling");

const appointment = {
  id: "appointment-1", appointment_number: "APT-000001", branch_id: "branch-1",
  customer_id: "customer-1", service_location_id: "location-1", status: "scheduled",
  arrival_window_start_at: "2026-08-13T13:00:00Z", arrival_window_end_at: "2026-08-13T15:00:00Z",
};

describe("SchedulingRoute", () => {
  beforeEach(() => { permissions = new Set(["COMPANY_SCHEDULING_READ"]); vi.clearAllMocks(); });

  it("disables the schedule query without read authority", () => {
    permissions = new Set();
    vi.mocked(useAppointments).mockReturnValue({ isLoading: false } as never);
    render(<MemoryRouter><SchedulingRoute /></MemoryRouter>);
    expect(screen.getByText(/not authorized to view Scheduling/i)).toBeVisible();
    expect(useAppointments).toHaveBeenCalledWith(expect.any(Object), false);
  });

  it("shows authoritative appointments and links to detail", () => {
    vi.mocked(useAppointments).mockReturnValue({ isLoading: false, isError: false, data: { items: [appointment], total_count: 1, page: 1, page_size: 50 } } as never);
    render(<MemoryRouter><SchedulingRoute /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Scheduling" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /APT-000001/ })).toHaveAttribute("href", "/appointments/appointment-1");
  });

  it("applies Branch and status filters to the authoritative query", async () => {
    vi.mocked(useAppointments).mockReturnValue({ isLoading: false, isError: false, data: { items: [], total_count: 0, page: 1, page_size: 50 } } as never);
    render(<MemoryRouter><SchedulingRoute /></MemoryRouter>);
    await userEvent.selectOptions(screen.getByLabelText("Branch"), "branch-1");
    await userEvent.selectOptions(screen.getByLabelText("Appointment status"), "confirmed");
    const latest = vi.mocked(useAppointments).mock.calls.at(-1)?.[0];
    expect(latest).toEqual(expect.objectContaining({ branchId: "branch-1", status: ["confirmed"], page: 1, pageSize: 50 }));
  });

  it("reports a truthful empty day", () => {
    vi.mocked(useAppointments).mockReturnValue({ isLoading: false, isError: false, data: { items: [], total_count: 0, page: 1, page_size: 50 } } as never);
    render(<MemoryRouter><SchedulingRoute /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "No appointments found" })).toBeInTheDocument();
  });
});
