import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useJobs } from "../hooks/useJobs";
import { useAppointments } from "../hooks/useScheduling";
import { DispatchRoute } from "./DispatchRoute";

vi.mock("../auth", () => ({ useAuth: () => ({ activeCompany: { id: "company-1", branches: [{ id: "branch-1", name: "Main", code: "MAIN" }, { id: "branch-2", name: "North", code: "NORTH" }] } }) }));
vi.mock("../hooks/useJobs");
vi.mock("../hooks/useScheduling");

const refetchAppointments = vi.fn();
const refetchJobs = vi.fn();
const appointment = { id: "appointment-1", appointment_number: "APT-000001", status: "scheduled", arrival_window_start_at: "2026-07-23T13:00:00Z", arrival_window_end_at: "2026-07-23T15:00:00Z", expected_duration_minutes: 90 };
const job = { id: "job-1", job_number: "JOB-000001", status: "paused", priority: "urgent", customer_display_name: "Taylor Home", service_location_label: "10 Main Street", updated_at: "2026-07-23T12:00:00Z" };

describe("DispatchRoute", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAppointments).mockReturnValue({ isLoading: false, error: null, data: { items: [appointment], total_count: 1 }, refetch: refetchAppointments } as never);
    vi.mocked(useJobs).mockReturnValue({ isLoading: false, error: null, data: { items: [job], total_count: 1 }, refetch: refetchJobs } as never);
  });
  it("renders authoritative queues, summaries, and cross-workspace links", () => {
    render(<MemoryRouter><DispatchRoute /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Dispatch" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "APT-000001" })).toHaveAttribute("href", "/appointments/appointment-1");
    expect(screen.getByRole("link", { name: "JOB-000001" })).toHaveAttribute("href", "/jobs/job-1");
    expect(screen.getAllByText("Paused")).toHaveLength(2);
    expect(screen.getByText("High priority")).toBeInTheDocument();
  });
  it("updates domain queries when Branch and date scope change", () => {
    render(<MemoryRouter><DispatchRoute /></MemoryRouter>);
    fireEvent.change(screen.getByRole("combobox", { name: "Branch" }), { target: { value: "branch-2" } });
    expect(useAppointments).toHaveBeenLastCalledWith(expect.objectContaining({ branchId: "branch-2" }), true);
    expect(useJobs).toHaveBeenLastCalledWith(expect.objectContaining({ branchId: "branch-2" }));
    fireEvent.click(screen.getByRole("button", { name: "Next day" }));
    const latest = vi.mocked(useAppointments).mock.calls.at(-1)?.[0];
    expect(latest?.startAt).not.toBe(vi.mocked(useAppointments).mock.calls[0][0].startAt);
  });
  it("isolates a failed Appointment section from successful Jobs", () => {
    vi.mocked(useAppointments).mockReturnValue({ isLoading: false, error: { isAxiosError: true, message: "Network Error" }, data: undefined, refetch: refetchAppointments } as never);
    render(<MemoryRouter><DispatchRoute /></MemoryRouter>);
    expect(screen.getByText("Appointments unavailable")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "JOB-000001" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(refetchAppointments).toHaveBeenCalled();
  });
  it("renders independent empty and loading states", () => {
    vi.mocked(useAppointments).mockReturnValue({ isLoading: true, error: null, data: undefined, refetch: refetchAppointments } as never);
    vi.mocked(useJobs).mockReturnValue({ isLoading: false, error: null, data: { items: [], total_count: 0 }, refetch: refetchJobs } as never);
    render(<MemoryRouter><DispatchRoute /></MemoryRouter>);
    expect(screen.getByRole("status", { name: "Loading Appointments" })).toBeInTheDocument();
    expect(screen.getByText("No operational Jobs")).toBeInTheDocument();
  });
  it("uses server pagination independently for each queue", () => {
    vi.mocked(useAppointments).mockReturnValue({ isLoading: false, error: null, data: { items: [appointment], total_count: 51 }, refetch: refetchAppointments } as never);
    vi.mocked(useJobs).mockReturnValue({ isLoading: false, error: null, data: { items: [job], total_count: 21, total_pages: 2 }, refetch: refetchJobs } as never);
    render(<MemoryRouter><DispatchRoute /></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: "Next Appointment page" }));
    expect(useAppointments).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }), true);
    fireEvent.click(screen.getByRole("button", { name: "Next Job page" }));
    expect(useJobs).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }));
  });
});
