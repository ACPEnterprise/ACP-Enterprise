import { render, screen, waitFor, within } from "@testing-library/react";
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
const rescheduleMutate = vi.hoisted(() => vi.fn());
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
const expectedLocalInput = (value: string) => {
  const date = new Date(value);
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
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
      mutate: rescheduleMutate,
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
    expect(screen.getAllByRole("button", { name: /APT-000001/ })).toHaveLength(3);
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

  it("exposes CSR booking only with Customer read plus Scheduling and Job manage authority", () => {
    vi.mocked(useAppointments).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [], total_count: 0, page: 1, page_size: 100 },
    } as never);
    render(<MemoryRouter><SchedulingRoute /></MemoryRouter>);
    expect(screen.queryByRole("button", { name: "Book customer work" })).not.toBeInTheDocument();

    permissions.add("COMPANY_SCHEDULING_MANAGE");
    permissions.add("COMPANY_JOB_MANAGE");
    permissions.add("COMPANY_CUSTOMER_READ");
    render(<MemoryRouter><SchedulingRoute /></MemoryRouter>);
    expect(screen.getByRole("button", { name: "Book customer work" })).toBeVisible();
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

  it("opens directly in the Dispatch calendar perspective", () => {
    vi.mocked(useAppointments).mockReturnValue({ isLoading: false, isError: false, data: { items: [appointment], total_count: 1, page: 1, page_size: 100 } } as never);
    render(<MemoryRouter initialEntries={["/scheduling?perspective=dispatch"]}><SchedulingRoute /></MemoryRouter>);
    expect(screen.getByRole("region", { name: "Dispatch timeline" })).toBeVisible();
  });

  it("uses Month as an operating calendar and requires confirmation before moving work", async () => {
    permissions.add("COMPANY_SCHEDULING_MANAGE");
    vi.mocked(useAppointments).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [appointment], total_count: 1, page: 1, page_size: 100 },
    } as never);
    render(<MemoryRouter><SchedulingRoute /></MemoryRouter>);
    const date = screen.getByLabelText("Service date");
    await userEvent.clear(date);
    await userEvent.type(date, "2026-08-13");
    await userEvent.click(screen.getByRole("button", { name: "Month" }));
    await userEvent.click(within(screen.getByRole("region", { name: "Month calendar" })).getByRole("button", { name: /APT-000001.*UNASSIGNED/i }));
    expect(screen.getByRole("link", { name: "Open Customer" })).toHaveAttribute("href", "/customers/customer-1");
    expect(screen.getAllByText("Customer context unavailable").at(-1)).toBeVisible();
    await userEvent.clear(screen.getByLabelText("New start"));
    await userEvent.type(screen.getByLabelText("New start"), "2026-08-14T09:00");
    await userEvent.clear(screen.getByLabelText("New arrival-window end"));
    await userEvent.type(screen.getByLabelText("New arrival-window end"), "2026-08-14T12:00");
    await userEvent.clear(screen.getByLabelText("Duration in minutes"));
    await userEvent.type(screen.getByLabelText("Duration in minutes"), "90");
    await userEvent.click(screen.getByRole("button", { name: "Review new time" }));
    expect(rescheduleMutate).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "Move this appointment?" })).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Confirm new time" }));
    expect(rescheduleMutate).toHaveBeenCalledWith(expect.objectContaining({
      input: expect.objectContaining({
        arrival_window_start_at: new Date("2026-08-14T09:00").toISOString(),
        arrival_window_end_at: new Date("2026-08-14T12:00").toISOString(),
        expected_duration_minutes: 90,
      }),
    }), expect.any(Object));
  });

  it("reconciles selected appointment detail after the authoritative calendar refreshes", async () => {
    permissions.add("COMPANY_SCHEDULING_MANAGE");
    vi.mocked(useAppointments).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [appointment], total_count: 1, page: 1, page_size: 100 },
    } as never);
    const rendered = render(<MemoryRouter><SchedulingRoute /></MemoryRouter>);
    await userEvent.click(screen.getAllByRole("button", { name: /APT-000001/ })[0]);
    expect(screen.getByLabelText("New start")).toHaveValue(expectedLocalInput("2026-08-13T13:00:00Z"));

    vi.mocked(useAppointments).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        items: [{ ...appointment, arrival_window_start_at: "2026-08-13T14:00:00Z" }],
        total_count: 1,
        page: 1,
        page_size: 100,
      },
    } as never);
    rendered.rerender(<MemoryRouter><SchedulingRoute /></MemoryRouter>);
    await waitFor(() => expect(screen.getByLabelText("New start")).toHaveValue(expectedLocalInput("2026-08-13T14:00:00Z")));
  });

  it("expands and selects every appointment on a crowded Month day before an explicit Day drill-down", async () => {
    const crowded = Array.from({ length: 5 }, (_, index) => ({
      ...appointment,
      id: `appointment-${index + 1}`,
      appointment_number: `APT-00000${index + 1}`,
    }));
    vi.mocked(useAppointments).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: crowded, total_count: 5, page: 1, page_size: 100 },
    } as never);
    render(<MemoryRouter><SchedulingRoute /></MemoryRouter>);
    const date = screen.getByLabelText("Service date");
    await userEvent.clear(date);
    await userEvent.type(date, "2026-08-13");
    await userEvent.selectOptions(screen.getByLabelText("Technician"), "__unassigned");
    await userEvent.click(screen.getByRole("button", { name: "Month" }));

    const month = screen.getByRole("region", { name: "Month calendar" });
    const overflow = within(month).getByRole("button", { name: /Show all 5 appointments/ });
    expect(overflow).toHaveTextContent("+2 more");
    expect(overflow).toHaveAttribute("aria-expanded", "false");
    expect(within(month).getAllByRole("button", { name: /APT-00000/ })).toHaveLength(3);

    await userEvent.click(overflow);
    expect(screen.getByRole("region", { name: "Month calendar" })).toBeVisible();
    expect(overflow).toHaveAttribute("aria-expanded", "true");
    for (const item of crowded) {
      expect(within(month).getByRole("button", { name: new RegExp(item.appointment_number) })).toBeVisible();
    }
    await userEvent.click(within(month).getByRole("button", { name: /APT-000005/ }));
    expect(screen.getByRole("link", { name: "Open Appointment" })).toHaveAttribute("href", "/appointments/appointment-5");

    await userEvent.click(within(month).getByRole("button", { name: /Open 8\/13\/2026 day schedule/ }));
    expect(screen.getByRole("region", { name: "Day calendar" })).toBeVisible();
    expect(screen.getByLabelText("Technician")).toHaveValue("__unassigned");
  });

  it("surfaces appointment-level assignment gaps in Unassigned", async () => {
    vi.mocked(useAppointments).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [appointment], total_count: 1, page: 1, page_size: 100 },
    } as never);
    render(<MemoryRouter><SchedulingRoute /></MemoryRouter>);
    await userEvent.click(screen.getByRole("button", { name: "Unassigned" }));
    expect(screen.getByRole("heading", { name: "Appointments needing assignment or time" })).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: /APT-000001/ }));
    expect(screen.getByText("Customer context unavailable")).toBeVisible();
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
