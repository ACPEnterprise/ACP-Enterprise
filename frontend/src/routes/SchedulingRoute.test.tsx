import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useDispatchBoard } from "../hooks/useDispatch";
import { useJobs } from "../hooks/useJobs";
import {
  useAppointments,
  useRescheduleAppointment,
} from "../hooks/useScheduling";
import { SchedulingRoute } from "./SchedulingRoute";

let permissions = new Set(["COMPANY_SCHEDULING_READ"]);
vi.mock("../auth", () => ({
  useAuth: () => ({
    activeCompany: { branches: [{ id: "branch-1", name: "Main Branch" }] },
  }),
  useHasPermission: (code: string) => permissions.has(code),
}));
vi.mock("../hooks/useScheduling");
vi.mock("../hooks/useDispatch");
vi.mock("../hooks/useJobs");

const appointment = {
  id: "appointment-1",
  appointment_number: "APT-000001",
  branch_id: "branch-1",
  customer_id: "customer-1",
  service_location_id: "location-1",
  status: "scheduled",
  arrival_window_start_at: "2026-08-13T13:00:00Z",
  arrival_window_end_at: "2026-08-13T15:00:00Z",
};

describe("SchedulingRoute", () => {
  beforeEach(() => {
    permissions = new Set([
      "COMPANY_SCHEDULING_READ",
      "COMPANY_DISPATCH_READ",
      "COMPANY_JOB_READ",
    ]);
    vi.clearAllMocks();
    vi.mocked(useDispatchBoard).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [], total_count: 0 },
    } as never);
    vi.mocked(useJobs).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [], total_count: 0, total_pages: 0 },
    } as never);
    vi.mocked(useRescheduleAppointment).mockReturnValue({
      isPending: false,
      isError: false,
      isSuccess: false,
      mutate: vi.fn(),
    } as never);
  });

  it("disables the schedule query without read authority", () => {
    permissions = new Set();
    vi.mocked(useAppointments).mockReturnValue({ isLoading: false } as never);
    render(
      <MemoryRouter>
        <SchedulingRoute />
      </MemoryRouter>,
    );
    expect(
      screen.getByText(/not authorized to view Scheduling/i),
    ).toBeVisible();
    expect(useAppointments).toHaveBeenCalledWith(expect.any(Object), false);
  });

  it("shows authoritative appointments and links to detail", () => {
    vi.mocked(useAppointments).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [appointment], total_count: 1, page: 1, page_size: 50 },
    } as never);
    render(
      <MemoryRouter>
        <SchedulingRoute />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("heading", { name: "Schedule & Dispatch" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Day calendar" })).toBeVisible();
    expect(screen.getByRole("region", { name: "Day agenda" })).toBeVisible();
    expect(screen.getAllByRole("button", { name: /APT-000001/ })).toHaveLength(
      2,
    );
  });

  it("applies Branch and status filters to the authoritative query", async () => {
    vi.mocked(useAppointments).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [], total_count: 0, page: 1, page_size: 50 },
    } as never);
    render(
      <MemoryRouter>
        <SchedulingRoute />
      </MemoryRouter>,
    );
    await userEvent.selectOptions(screen.getByLabelText("Branch"), "branch-1");
    await userEvent.selectOptions(
      screen.getByLabelText("Appointment status"),
      "confirmed",
    );
    const latest = vi.mocked(useAppointments).mock.calls.at(-1)?.[0];
    expect(latest).toEqual(
      expect.objectContaining({
        branchId: "branch-1",
        status: ["confirmed"],
        page: 1,
        pageSize: 100,
      }),
    );
  });

  it("reports a truthful empty day", () => {
    vi.mocked(useAppointments).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [], total_count: 0, page: 1, page_size: 50 },
    } as never);
    render(
      <MemoryRouter>
        <SchedulingRoute />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("heading", { name: "No scheduled appointments" }),
    ).toBeInTheDocument();
  });

  it("offers a planning week and accessible non-drag calendar controls", async () => {
    vi.mocked(useAppointments).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [appointment], total_count: 1, page: 1, page_size: 100 },
    } as never);
    render(
      <MemoryRouter>
        <SchedulingRoute />
      </MemoryRouter>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Week" }));
    expect(screen.getByRole("region", { name: "Week calendar" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Previous week" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Next week" })).toBeVisible();
  });

  it("projects the same appointments across Work Week, Month, and Dispatch", async () => {
    vi.mocked(useAppointments).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [appointment], total_count: 1, page: 1, page_size: 100 },
    } as never);
    render(
      <MemoryRouter>
        <SchedulingRoute />
      </MemoryRouter>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Work Week" }));
    expect(
      screen.getByRole("region", { name: "Work Week calendar" }),
    ).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Month" }));
    expect(screen.getByRole("region", { name: "Month calendar" })).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Day" }));
    await userEvent.click(screen.getByRole("button", { name: "Dispatch" }));
    expect(
      screen.getByRole("region", { name: "Dispatch timeline" }),
    ).toBeVisible();
    expect(screen.getByText(/review-only/i)).toBeVisible();
  });

  it("offers Unassigned as an explicit projection without a second engine", async () => {
    vi.mocked(useAppointments).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [], total_count: 0, page: 1, page_size: 100 },
    } as never);
    render(
      <MemoryRouter>
        <SchedulingRoute />
      </MemoryRouter>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Unassigned" }));
    expect(
      screen.getByRole("heading", { name: "Needs scheduling" }),
    ).toBeVisible();
    expect(
      screen.queryByRole("heading", { name: "Appointment details" }),
    ).toBeInTheDocument();
  });

  it("shows unscheduled Jobs as a distinct office queue", () => {
    vi.mocked(useAppointments).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [], total_count: 0, page: 1, page_size: 100 },
    } as never);
    vi.mocked(useJobs).mockReturnValue({
      isLoading: false,
      data: {
        items: [
          {
            id: "job-1",
            job_number: "JOB-1",
            customer_display_name: "County Customer",
            service_location_label: "Main Street",
            priority: "high",
            earliest_appointment_start_at: null,
          },
        ],
        total_count: 1,
        total_pages: 1,
      },
    } as never);
    render(
      <MemoryRouter>
        <SchedulingRoute />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("heading", { name: "Needs scheduling" }),
    ).toBeVisible();
    expect(screen.getByRole("link", { name: /JOB-1/ })).toHaveAttribute(
      "href",
      "/jobs/job-1",
    );
  });

  it("renders technician and unassigned lanes without claiming open time is availability", () => {
    const second = {
      ...appointment,
      id: "appointment-2",
      appointment_number: "APT-000002",
    };
    vi.mocked(useAppointments).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        items: [appointment, second],
        total_count: 2,
        page: 1,
        page_size: 100,
      },
    } as never);
    vi.mocked(useDispatchBoard).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        total_count: 2,
        items: [
          {
            appointment_id: "appointment-1",
            appointment_number: "APT-000001",
            job_id: null,
            branch_id: "branch-1",
            status: "scheduled",
            window_start_at: appointment.arrival_window_start_at,
            window_end_at: appointment.arrival_window_end_at,
            assignment: {
              primary_employee_name: "Alex Technician",
              arrival_state: "en_route",
            },
          },
          {
            appointment_id: "appointment-2",
            appointment_number: "APT-000002",
            job_id: null,
            branch_id: "branch-1",
            status: "scheduled",
            window_start_at: appointment.arrival_window_start_at,
            window_end_at: appointment.arrival_window_end_at,
            assignment: null,
          },
        ],
      },
    } as never);
    render(
      <MemoryRouter>
        <SchedulingRoute />
      </MemoryRouter>,
    );
    expect(
      screen
        .getAllByText("Alex Technician")
        .some((item) => item.tagName === "DIV"),
    ).toBe(true);
    expect(
      screen.getAllByText("Unassigned").some((item) => item.tagName === "DIV"),
    ).toBe(true);
    expect(
      screen.getByText(/not verified technician availability/i),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: /APT-000001.*EN ROUTE/i }),
    ).toBeVisible();
  });
});
