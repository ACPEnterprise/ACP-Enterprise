import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useDispatchBoard } from "../hooks/useDispatch";
import { useJobs } from "../hooks/useJobs";
import { useCalendarPlacement } from "../hooks/useOperations";
import {
  useBranchCalendarRoster,
  useBranchSchedulingPolicy,
  useAppointments,
  useRescheduleAppointment,
} from "../hooks/useScheduling";
import { SchedulingRoute } from "./SchedulingRoute";

let permissions = new Set(["COMPANY_SCHEDULING_READ"]);
const rescheduleMutate = vi.hoisted(() => vi.fn());
const placementMutateAsync = vi.hoisted(() => vi.fn());
vi.mock("../auth", () => ({
  useAuth: () => ({
    activeCompany: { branches: [{ id: "branch-1", name: "Main Branch" }] },
  }),
  useHasPermission: (code: string) => permissions.has(code),
}));
vi.mock("../hooks/useScheduling");
vi.mock("../hooks/useDispatch");
vi.mock("../hooks/useJobs");
vi.mock("../hooks/useOperations", () => ({ useCalendarPlacement: vi.fn() }));

const appointment = {
  id: "appointment-1",
  appointment_number: "APT-000001",
  branch_id: "branch-1",
  customer_id: "customer-1",
  service_location_id: "location-1",
  status: "scheduled",
  arrival_window_start_at: "2026-08-13T13:00:00Z",
  arrival_window_end_at: "2026-08-13T15:00:00Z",
  capacity_units: "1.00",
  capacity_state: "reserved",
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
    vi.mocked(useCalendarPlacement).mockReturnValue({
      mutateAsync: placementMutateAsync,
    } as never);
    vi.mocked(useBranchSchedulingPolicy).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        branch_id: "branch-1",
        timezone: "America/New_York",
        status: "ACTIVE",
        readiness: "SCHEDULING_READY",
        blockers: [],
        version: 1,
        booking_horizon_days: 365,
        minimum_notice_minutes: 0,
        slot_interval_minutes: 15,
        default_capacity_units: "2.00",
        weekly_intervals: Array.from({ length: 7 }, (_, day_of_week) => ({
          day_of_week,
          start_minute: 420,
          end_minute: 1140,
          capacity_units: "2.00",
        })),
        exceptions: [],
      },
    } as never);
    vi.mocked(useBranchCalendarRoster).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        branch_id: "branch-1",
        window_start_at: "2026-08-13T00:00:00Z",
        window_end_at: "2026-08-14T00:00:00Z",
        technicians: [],
      },
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

  it("denies a FIELD_TECH profile the company-wide office Calendar", () => {
    permissions = new Set([
      "COMPANY_EMPLOYEE_OPERATIONS_OWN_DAY_READ",
      "COMPANY_JOB_EXECUTE",
    ]);
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
      screen.getByRole("heading", { name: "Service Board" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Day calendar" })).toBeVisible();
    const dayCalendar = within(
      screen.getByRole("region", { name: "Day calendar" }),
    );
    expect(dayCalendar.getAllByText(":15").length).toBeGreaterThan(0);
    expect(dayCalendar.getAllByText(":30").length).toBeGreaterThan(0);
    expect(dayCalendar.getAllByText(":45").length).toBeGreaterThan(0);
    expect(screen.getByRole("region", { name: "Day agenda" })).toBeVisible();
    expect(screen.getAllByRole("button", { name: /APT-000001/ })).toHaveLength(
      2,
    );
    const block = dayCalendar.getByRole("button", { name: /APT-000001/ });
    expect(block).toHaveStyle({ top: "120px", height: "120px" });
  });

  it("shows current time on today's Schedule and Dispatch timelines", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 13, 10, 30));
    vi.mocked(useAppointments).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [appointment], total_count: 1, page: 1, page_size: 100 },
    } as never);
    try {
      const day = render(
        <MemoryRouter>
          <SchedulingRoute />
        </MemoryRouter>,
      );
      expect(screen.getByLabelText("Current time")).toBeVisible();
      day.unmount();
      render(
        <MemoryRouter
          initialEntries={[
            "/scheduling?date=2026-08-13&perspective=dispatch&view=day",
          ]}
        >
          <SchedulingRoute />
        </MemoryRouter>,
      );
      expect(screen.getByLabelText("Current time")).toBeVisible();
    } finally {
      vi.useRealTimers();
    }
  });

  it("offers bounded recovery when schedule or Job context projections fail", async () => {
    const appointmentRefetch = vi.fn();
    const dispatchRefetch = vi.fn();
    const jobsRefetch = vi.fn();
    vi.mocked(useAppointments).mockReturnValue({
      isLoading: false,
      isError: true,
      error: new Error("schedule failed"),
      refetch: appointmentRefetch,
    } as never);
    vi.mocked(useDispatchBoard).mockReturnValue({
      isLoading: false,
      isError: true,
      error: new Error("dispatch failed"),
      refetch: dispatchRefetch,
    } as never);
    vi.mocked(useJobs).mockReturnValue({
      isLoading: false,
      isError: true,
      error: new Error("jobs failed"),
      refetch: jobsRefetch,
    } as never);
    render(
      <MemoryRouter>
        <SchedulingRoute />
      </MemoryRouter>,
    );
    expect(
      screen.getByText(/Appointment times remain authoritative and usable/),
    ).toBeVisible();
    await userEvent.click(
      screen.getByRole("button", { name: "Retry schedule" }),
    );
    expect(appointmentRefetch).toHaveBeenCalledOnce();
    expect(dispatchRefetch).toHaveBeenCalledOnce();
    await userEvent.click(
      screen.getByRole("button", { name: "Retry Job context" }),
    );
    expect(jobsRefetch).toHaveBeenCalledOnce();
  });

  it("offers an explicit authoritative refresh without implying realtime updates", async () => {
    const appointmentRefetch = vi.fn();
    const dispatchRefetch = vi.fn();
    const jobsRefetch = vi.fn();
    vi.mocked(useAppointments).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [appointment], total_count: 1, page: 1, page_size: 100 },
      refetch: appointmentRefetch,
    } as never);
    vi.mocked(useDispatchBoard).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [], total_count: 0 },
      refetch: dispatchRefetch,
    } as never);
    vi.mocked(useJobs).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [], total_count: 0, total_pages: 0 },
      refetch: jobsRefetch,
    } as never);
    render(
      <MemoryRouter>
        <SchedulingRoute />
      </MemoryRouter>,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Refresh authoritative calendar" }),
    );
    expect(appointmentRefetch).toHaveBeenCalledTimes(2);
    expect(dispatchRefetch).toHaveBeenCalledOnce();
    expect(jobsRefetch).toHaveBeenCalledOnce();
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

  it("keeps the roster calendar visible on a truthful empty day", () => {
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
    expect(screen.getByRole("region", { name: "Day calendar" })).toBeVisible();
    expect(
      screen.getByText(/available technician lanes remain visible/i),
    ).toBeVisible();
  });

  it("blocks a normal calendar when Branch Scheduling setup is required", () => {
    vi.mocked(useAppointments).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [], total_count: 0, page: 1, page_size: 100 },
    } as never);
    vi.mocked(useBranchSchedulingPolicy).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        readiness: "SCHEDULING_SETUP_REQUIRED",
        blockers: ["NO_ACTIVE_CALENDAR"],
      },
    } as never);
    render(
      <MemoryRouter>
        <SchedulingRoute />
      </MemoryRouter>,
    );
    expect(screen.getByText("SCHEDULING SETUP REQUIRED")).toBeVisible();
    expect(
      screen.getByRole("link", {
        name: /Administration.*Branch Scheduling Setup/i,
      }),
    ).toHaveAttribute("href", "/administration");
    expect(
      screen.queryByRole("region", { name: "Day calendar" }),
    ).not.toBeInTheDocument();
  });

  it("shows Branch roster technicians even when they have zero Appointments", () => {
    vi.mocked(useAppointments).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [], total_count: 0, page: 1, page_size: 100 },
    } as never);
    vi.mocked(useBranchCalendarRoster).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        technicians: [
          {
            employee_id: "employee-michael",
            employee_number: "E-1",
            display_name: "Michael Brian",
            job_title: "Technician",
            readiness: "AVAILABLE",
            readiness_reasons: [],
            availability_confidence: "branch_schedule",
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
        .getAllByText("Michael Brian")
        .some((item) => item.tagName === "DIV"),
    ).toBe(true);
    expect(screen.getByText("Available roster")).toBeVisible();
  });

  it("exposes CSR booking only with Customer read plus Scheduling and Job manage authority", () => {
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
    expect(
      screen.queryByRole("button", { name: "Book customer work" }),
    ).not.toBeInTheDocument();

    permissions.add("COMPANY_SCHEDULING_MANAGE");
    permissions.add("COMPANY_JOB_MANAGE");
    permissions.add("COMPANY_CUSTOMER_READ");
    render(
      <MemoryRouter>
        <SchedulingRoute />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("button", { name: "Book customer work" }),
    ).toBeVisible();
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

  it("renders a technician-lane Week grid with open capacity and multi-day Job visits", async () => {
    const nextVisit = {
      ...appointment,
      id: "appointment-2",
      appointment_number: "APT-000002",
      arrival_window_start_at: "2026-08-14T13:00:00Z",
      arrival_window_end_at: "2026-08-14T15:00:00Z",
    };
    vi.mocked(useAppointments).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        items: [appointment, nextVisit],
        total_count: 2,
        page: 1,
        page_size: 100,
      },
    } as never);
    vi.mocked(useBranchCalendarRoster).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        technicians: [
          {
            employee_id: "employee-alex",
            employee_number: "E-1",
            display_name: "Alex Technician",
            job_title: null,
            readiness: "AVAILABLE",
            readiness_reasons: [],
            availability_confidence: "branch_schedule",
          },
        ],
      },
    } as never);
    vi.mocked(useDispatchBoard).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        total_count: 2,
        items: [appointment, nextVisit].map((item) => ({
          appointment_id: item.id,
          appointment_number: item.appointment_number,
          job_id: "job-multi",
          branch_id: "branch-1",
          status: "scheduled",
          window_start_at: item.arrival_window_start_at,
          window_end_at: item.arrival_window_end_at,
          assignment: {
            id: `assignment-${item.id}`,
            appointment_id: item.id,
            appointment_number: item.appointment_number,
            job_id: "job-multi",
            company_id: "company-1",
            branch_id: "branch-1",
            primary_employee_id: "employee-alex",
            primary_employee_name: "Alex Technician",
            status: "assigned",
            arrival_state: "pending",
            active_exception_code: null,
            assignment_reason: "scheduled",
            window_start_at: item.arrival_window_start_at,
            window_end_at: item.arrival_window_end_at,
            effective_at: item.arrival_window_start_at,
            released_at: null,
            version: 1,
            crew_members: [],
          },
        })),
      },
    } as never);
    render(
      <MemoryRouter initialEntries={["/scheduling?date=2026-08-13"]}>
        <SchedulingRoute />
      </MemoryRouter>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Week" }));
    const week = screen.getByRole("region", { name: "Week calendar" });
    expect(within(week).getAllByText("Alex Technician").length).toBeGreaterThan(
      0,
    );
    expect(
      within(week).getAllByRole("button", { name: /Alex Technician/ }).length,
    ).toBeGreaterThan(0);
    expect(within(week).getAllByText("Customer unavailable").length).toBeGreaterThanOrEqual(2);
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
    expect(
      screen.getByRole("region", { name: "Month calendar" }),
    ).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Day" }));
    await userEvent.click(screen.getByRole("button", { name: "Dispatch" }));
    expect(screen.getByRole("region", { name: "Week calendar" })).toBeVisible();
  });

  it("opens directly in the Dispatch calendar perspective", () => {
    vi.mocked(useAppointments).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [appointment], total_count: 1, page: 1, page_size: 100 },
    } as never);
    render(
      <MemoryRouter initialEntries={["/scheduling?perspective=dispatch"]}>
        <SchedulingRoute />
      </MemoryRouter>,
    );
    expect(screen.getByRole("region", { name: "Week calendar" })).toBeVisible();
  });

  it("restores a direct-linked operating scope instead of resetting the CSR workspace", async () => {
    vi.mocked(useAppointments).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [appointment], total_count: 1, page: 1, page_size: 100 },
    } as never);
    render(
      <MemoryRouter
        initialEntries={[
          "/scheduling?date=2026-08-13&view=month&perspective=schedule&branch=branch-1&status=scheduled&technician=__unassigned&search=Taylor&jobStatus=ready&priority=emergency&queue=scheduled_unassigned&order=priority",
        ]}
      >
        <SchedulingRoute />
      </MemoryRouter>,
    );
    expect(screen.getByLabelText("Service date")).toHaveValue("2026-08-13");
    expect(
      screen.getByRole("region", { name: "Month calendar" }),
    ).toBeVisible();
    expect(screen.getByLabelText("Branch")).toHaveValue("branch-1");
    expect(screen.getByLabelText("Appointment status")).toHaveValue(
      "scheduled",
    );
    expect(screen.getByLabelText("Technician")).toHaveValue("__unassigned");
    expect(screen.getByLabelText("Search schedule")).toHaveValue("Taylor");
    await userEvent.click(screen.getByRole("button", { name: "Unassigned" }));
    expect(screen.getByLabelText("Queue Job status")).toHaveValue("ready");
    expect(screen.getByLabelText("Queue priority")).toHaveValue("emergency");
    expect(screen.getByLabelText("Queue state")).toHaveValue(
      "scheduled_unassigned",
    );
    expect(screen.getByLabelText("Queue order")).toHaveValue("priority");
  });

  it("uses Month as an operating calendar and requires confirmation before moving work", async () => {
    permissions.add("COMPANY_SCHEDULING_MANAGE");
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
    const date = screen.getByLabelText("Service date");
    await userEvent.clear(date);
    await userEvent.type(date, "2026-08-13");
    await userEvent.click(screen.getByRole("button", { name: "Month" }));
    await userEvent.click(
      within(screen.getByRole("region", { name: "Month calendar" })).getByRole(
        "button",
        { name: /APT-000001.*UNASSIGNED/i },
      ),
    );
    expect(screen.getByRole("link", { name: "Open Customer" })).toHaveAttribute(
      "href",
      expect.stringMatching(/^\/customers\/customer-1\?returnTo=/),
    );
    expect(
      screen.getAllByText("Customer context unavailable").at(-1),
    ).toBeVisible();
    await userEvent.clear(screen.getByLabelText("New start"));
    await userEvent.type(
      screen.getByLabelText("New start"),
      "2026-08-14T09:00",
    );
    await userEvent.clear(screen.getByLabelText("New arrival-window end"));
    await userEvent.type(
      screen.getByLabelText("New arrival-window end"),
      "2026-08-14T12:00",
    );
    await userEvent.clear(screen.getByLabelText("Duration in minutes"));
    await userEvent.type(screen.getByLabelText("Duration in minutes"), "90");
    await userEvent.click(
      screen.getByRole("button", { name: "Review new time" }),
    );
    expect(rescheduleMutate).not.toHaveBeenCalled();
    expect(
      screen.getByRole("dialog", { name: "Move this appointment?" }),
    ).toBeVisible();
    await userEvent.click(
      screen.getByRole("button", { name: "Confirm new time" }),
    );
    expect(rescheduleMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        input: expect.objectContaining({
          arrival_window_start_at: new Date("2026-08-14T09:00").toISOString(),
          arrival_window_end_at: new Date("2026-08-14T12:00").toISOString(),
          expected_duration_minutes: 90,
        }),
      }),
      expect.any(Object),
    );
  });

  it("labels imported capacity-unreconciled Appointments and blocks unsafe moves", async () => {
    permissions.add("COMPANY_SCHEDULING_MANAGE");
    const imported = {
      ...appointment,
      capacity_units: null,
      capacity_state: "legacy_unreconciled",
    };
    vi.mocked(useAppointments).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [imported], total_count: 1, page: 1, page_size: 100 },
    } as never);
    render(
      <MemoryRouter initialEntries={["/scheduling?date=2026-08-13"]}>
        <SchedulingRoute />
      </MemoryRouter>,
    );
    expect(
      screen.getAllByText(/IMPORTED \/.*CAPACITY.*RECONCILED/i).length,
    ).toBeGreaterThan(0);
    await userEvent.click(
      screen.getAllByRole("button", { name: /APT-000001/ })[0],
    );
    expect(
      screen.getAllByText("IMPORTED / NOT YET CAPACITY-RECONCILED").length,
    ).toBeGreaterThan(0);
    expect(
      screen.queryByRole("button", { name: "Review new time" }),
    ).not.toBeInTheDocument();
  });

  it("enables normal rescheduling when canonical reconciliation supplies capacity authority", async () => {
    permissions.add("COMPANY_SCHEDULING_MANAGE");
    vi.mocked(useAppointments).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        items: [
          {
            ...appointment,
            capacity_units: null,
            capacity_state: "legacy_unreconciled",
          },
        ],
        total_count: 1,
        page: 1,
        page_size: 100,
      },
    } as never);
    const rendered = render(
      <MemoryRouter initialEntries={["/scheduling?date=2026-08-13"]}>
        <SchedulingRoute />
      </MemoryRouter>,
    );
    await userEvent.click(
      screen.getAllByRole("button", { name: /APT-000001/ })[0],
    );
    expect(
      screen.getAllByText("IMPORTED / NOT YET CAPACITY-RECONCILED").length,
    ).toBeGreaterThan(0);

    vi.mocked(useAppointments).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        items: [
          {
            ...appointment,
            capacity_units: "1.00",
            capacity_state: "reserved",
            concurrency_version: 3,
          },
        ],
        total_count: 1,
        page: 1,
        page_size: 100,
      },
    } as never);
    rendered.rerender(
      <MemoryRouter initialEntries={["/scheduling?date=2026-08-13"]}>
        <SchedulingRoute />
      </MemoryRouter>,
    );

    expect(
      screen.queryByText("IMPORTED / NOT YET CAPACITY-RECONCILED"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Review new time" }),
    ).toBeVisible();
  });

  it("reconciles selected appointment detail after the authoritative calendar refreshes", async () => {
    permissions.add("COMPANY_SCHEDULING_MANAGE");
    vi.mocked(useAppointments).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [appointment], total_count: 1, page: 1, page_size: 100 },
    } as never);
    const rendered = render(
      <MemoryRouter>
        <SchedulingRoute />
      </MemoryRouter>,
    );
    await userEvent.click(
      screen.getAllByRole("button", { name: /APT-000001/ })[0],
    );
    expect(screen.getByLabelText("New start")).toHaveValue(
      expectedLocalInput("2026-08-13T13:00:00Z"),
    );

    vi.mocked(useAppointments).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        items: [
          { ...appointment, arrival_window_start_at: "2026-08-13T14:00:00Z" },
        ],
        total_count: 1,
        page: 1,
        page_size: 100,
      },
    } as never);
    rendered.rerender(
      <MemoryRouter>
        <SchedulingRoute />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByLabelText("New start")).toHaveValue(
        expectedLocalInput("2026-08-13T14:00:00Z"),
      ),
    );
  });

  it.each(["completed", "no_show", "cancelled"])(
    "does not offer a reschedule action for %s Appointment history",
    async (status) => {
      permissions.add("COMPANY_SCHEDULING_MANAGE");
      vi.mocked(useAppointments).mockReturnValue({
        isLoading: false,
        isError: false,
        data: {
          items: [{ ...appointment, status }],
          total_count: 1,
          page: 1,
          page_size: 100,
        },
      } as never);
      render(
        <MemoryRouter>
          <SchedulingRoute />
        </MemoryRouter>,
      );
      await userEvent.click(
        screen.getAllByRole("button", { name: /APT-000001/ })[0],
      );

      expect(screen.getByText("Appointment cannot be moved")).toBeVisible();
      expect(
        screen.getByText(
          new RegExp(`This Appointment is ${status.replaceAll("_", " ")}`, "i"),
        ),
      ).toBeVisible();
      expect(
        screen.queryByRole("button", { name: "Review new time" }),
      ).not.toBeInTheDocument();
    },
  );

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
    render(
      <MemoryRouter>
        <SchedulingRoute />
      </MemoryRouter>,
    );
    const date = screen.getByLabelText("Service date");
    await userEvent.clear(date);
    await userEvent.type(date, "2026-08-13");
    await userEvent.selectOptions(
      screen.getByLabelText("Technician"),
      "__unassigned",
    );
    await userEvent.click(screen.getByRole("button", { name: "Month" }));

    const month = screen.getByRole("region", { name: "Month calendar" });
    expect(within(month).getByLabelText("5 appointments")).toBeVisible();
    const overflow = within(month).getByRole("button", {
      name: /Show all 5 appointments/,
    });
    expect(overflow).toHaveTextContent("+2 more");
    expect(overflow).toHaveAttribute("aria-expanded", "false");
    expect(
      within(month).getAllByRole("button", { name: /APT-00000/ }),
    ).toHaveLength(3);

    await userEvent.click(overflow);
    expect(
      screen.getByRole("region", { name: "Month calendar" }),
    ).toBeVisible();
    expect(overflow).toHaveAttribute("aria-expanded", "true");
    for (const item of crowded) {
      expect(
        within(month).getByRole("button", {
          name: new RegExp(item.appointment_number),
        }),
      ).toBeVisible();
    }
    await userEvent.click(
      within(month).getByRole("button", { name: /APT-000005/ }),
    );
    expect(
      screen
        .getAllByRole("link", { name: "Open Appointment" })
        .find((link) =>
          link
            .getAttribute("href")
            ?.startsWith("/appointments/appointment-5?returnTo="),
        ),
    ).toBeDefined();

    await userEvent.click(
      within(month).getByRole("button", {
        name: /Open 8\/13\/2026 day schedule/,
      }),
    );
    expect(screen.getByRole("region", { name: "Day calendar" })).toBeVisible();
    expect(screen.getByLabelText("Technician")).toHaveValue("__unassigned");
  });

  it("surfaces appointment-level assignment gaps in Unassigned", async () => {
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
    await userEvent.click(screen.getByRole("button", { name: "Unassigned" }));
    expect(
      screen.getByRole("heading", { name: "Needs Scheduling work queue" }),
    ).toBeVisible();
    await userEvent.click(
      screen.getByRole("button", { name: "Select for assignment" }),
    );
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
      screen.getByRole("heading", { name: "Needs Scheduling work queue" }),
    ).toBeVisible();
    expect(
      screen.queryByRole("heading", { name: "Appointment details" }),
    ).toBeInTheDocument();
  });

  it("opens unscheduled Jobs from the compact attention indicator", async () => {
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
    await userEvent.click(
      screen.getByRole("button", { name: "Needs Scheduling 1" }),
    );
    expect(
      screen.getByRole("heading", { name: "Needs Scheduling work queue" }),
    ).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Open Job to schedule" }),
    ).toHaveAttribute(
      "href",
      expect.stringMatching(/^\/jobs\/job-1\?returnTo=/),
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
              id: "assignment-1",
              primary_employee_id: "employee-alex",
              primary_employee_name: "Alex Technician",
              status: "assigned",
              arrival_state: "en_route",
              crew_members: [],
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
      screen.getByText(/lane labels disclose roster availability authority/i),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: /APT-000001.*EN ROUTE/i }),
    ).toBeVisible();
  });

  it("moves canonical Dispatch reassignment from Unassigned to Michael Brian without reloading", () => {
    vi.mocked(useAppointments).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [appointment], total_count: 1, page: 1, page_size: 100 },
    } as never);
    const rendered = render(
      <MemoryRouter initialEntries={["/scheduling?date=2026-08-13"]}>
        <SchedulingRoute />
      </MemoryRouter>,
    );
    expect(screen.getAllByText("Unassigned").length).toBeGreaterThan(0);

    vi.mocked(useDispatchBoard).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        total_count: 1,
        items: [
          {
            appointment_id: appointment.id,
            appointment_number: appointment.appointment_number,
            job_id: "job-1",
            branch_id: "branch-1",
            status: "scheduled",
            window_start_at: appointment.arrival_window_start_at,
            window_end_at: appointment.arrival_window_end_at,
            assignment: {
              id: "assignment-michael",
              appointment_id: appointment.id,
              appointment_number: appointment.appointment_number,
              job_id: "job-1",
              company_id: "company-1",
              branch_id: "branch-1",
              primary_employee_id: "michael-brian",
              primary_employee_name: "Michael Brian",
              status: "assigned",
              arrival_state: "pending",
              active_exception_code: null,
              assignment_reason: "Office assignment",
              window_start_at: appointment.arrival_window_start_at,
              window_end_at: appointment.arrival_window_end_at,
              effective_at: appointment.arrival_window_start_at,
              released_at: null,
              version: 1,
              crew_members: [],
            },
          },
        ],
      },
    } as never);
    rendered.rerender(
      <MemoryRouter initialEntries={["/scheduling?date=2026-08-13"]}>
        <SchedulingRoute />
      </MemoryRouter>,
    );

    expect(screen.getAllByText("Michael Brian").length).toBeGreaterThan(0);
    expect(
      screen.getAllByRole("button", { name: /APT-000001.*Michael Brian/i })
        .length,
    ).toBeGreaterThan(0);
  });

  it("opens Dispatch calendar-first on the current week with stable whole-team lanes and compact filters", () => {
    vi.mocked(useAppointments).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [appointment], total_count: 1, page: 1, page_size: 100 },
    } as never);
    vi.mocked(useBranchCalendarRoster).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        technicians: [
          {
            employee_id: "employee-jason",
            employee_number: "E-2",
            display_name: "Jason",
            job_title: null,
            readiness: "AVAILABLE",
            readiness_reasons: [],
            availability_confidence: "branch_schedule",
          },
          {
            employee_id: "employee-alex",
            employee_number: "E-1",
            display_name: "Alex",
            job_title: null,
            readiness: "AVAILABLE",
            readiness_reasons: [],
            availability_confidence: "branch_schedule",
          },
        ],
      },
    } as never);

    render(
      <MemoryRouter
        initialEntries={["/scheduling?perspective=dispatch&date=2026-08-13"]}
      >
        <SchedulingRoute />
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: "Dispatch" })).toBeVisible();
    const week = screen.getByRole("region", { name: "Week calendar" });
    expect(within(week).getAllByText("Unassigned").length).toBeGreaterThanOrEqual(7);
    expect(within(week).getAllByText("Alex").length).toBeGreaterThanOrEqual(7);
    expect(within(week).getAllByText("Jason").length).toBeGreaterThanOrEqual(7);
    expect(screen.queryByLabelText("Dispatch filters")).not.toBeInTheDocument();
  });

  it("inherits day, technician, time, and Branch when an authorized dispatcher selects empty calendar space", async () => {
    permissions = new Set([
      "COMPANY_SCHEDULING_READ",
      "COMPANY_SCHEDULING_MANAGE",
      "COMPANY_DISPATCH_READ",
      "COMPANY_DISPATCH_MANAGE",
      "COMPANY_JOB_READ",
      "COMPANY_JOB_MANAGE",
      "COMPANY_CUSTOMER_READ",
    ]);
    vi.mocked(useAppointments).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [], total_count: 0, page: 1, page_size: 100 },
    } as never);
    vi.mocked(useBranchCalendarRoster).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        technicians: [
          {
            employee_id: "employee-alex",
            employee_number: "E-1",
            display_name: "Alex",
            job_title: null,
            readiness: "AVAILABLE",
            readiness_reasons: [],
            availability_confidence: "branch_schedule",
          },
        ],
      },
    } as never);
    render(
      <MemoryRouter
        initialEntries={[
          "/scheduling?perspective=dispatch&view=week&date=2026-08-13",
        ]}
      >
        <SchedulingRoute />
      </MemoryRouter>,
    );

    await userEvent.click(
      screen.getByRole("button", { name: "Schedule Alex on 8/13/2026" }),
    );
    expect(
      screen.getByRole("heading", { name: "What would you like to schedule?" }),
    ).toBeVisible();
    expect(screen.getByText(/Alex · Branch inherited/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Job" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Estimate" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Meeting" })).toBeDisabled();
  });
});
