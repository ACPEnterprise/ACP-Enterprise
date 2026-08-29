import { act, render, screen, waitFor } from "@testing-library/react-native";
import { createEmployeeOperationsService, dayAssignmentSchema } from "../src/api/employeeOperations";
import type { DayAssignment, EmployeeDay, EmployeeOperationsService } from "../src/api/employeeOperations";
import { ApiFailure } from "../src/api/types";
import { MyDayScreen } from "../src/screens/MyDayScreen";

const first: DayAssignment = {
  appointment_id: "10000000-0000-4000-8000-000000000001",
  appointment_number: "APT-SYNTH-01",
  appointment_status: "scheduled",
  job_id: "20000000-0000-4000-8000-000000000001",
  job_number: "JOB-SYNTH-01",
  job_status: "open",
  service_category: "Maintenance",
  window_start_at: "2026-08-28T12:00:00Z",
  window_end_at: "2026-08-28T14:00:00Z",
  assignment_role: "primary",
  assignment_status: "assigned",
  designation: null,
  customer_display_name: "Synthetic Customer One",
  service_location: { label: "Synthetic Site", address_line_1: "100 Example Way", address_line_2: null, city: "Example City", state: "NY", postal_code: "10001", country: "US" },
};
const second: DayAssignment = {
  ...first,
  appointment_id: "10000000-0000-4000-8000-000000000002",
  appointment_number: "APT-SYNTH-02",
  job_id: null,
  job_number: null,
  window_start_at: "2026-08-28T15:00:00Z",
  window_end_at: "2026-08-28T16:00:00Z",
  assignment_role: "crew",
  customer_display_name: "Synthetic Customer Two",
};
const day = (assignments: DayAssignment[] = [first, second]): EmployeeDay => ({ business_date: "2026-08-28", timezone: "America/New_York", assignments });

function harness(initial: EmployeeDay = day(), connected = true) {
  let result = initial;
  let listener: ((connected: boolean) => void) | undefined;
  const service: EmployeeOperationsService = { day: jest.fn(async () => result) };
  const network = { isConnected: jest.fn(async () => connected), subscribe: jest.fn((next: (value: boolean) => void) => { listener = next; return () => undefined; }) };
  return {
    service,
    network,
    setResult(next: EmployeeDay) { result = next; },
    setConnected(next: boolean) { connected = next; act(() => listener?.(next)); },
  };
}

describe("native employee My Day", () => {
  it("renders authorized assignments using server ordering and safe projection fields", async () => {
    const h = harness();
    render(<MyDayScreen service={h.service} network={h.network} />);
    expect(await screen.findByText("Synthetic Customer One")).toBeOnTheScreen();
    const cards = screen.getAllByLabelText(/^Open assignment detail/);
    expect(cards[0]).toHaveAccessibleName(/Synthetic Customer One/);
    expect(cards[1]).toHaveAccessibleName(/Synthetic Customer Two/);
    expect(screen.getAllByText("100 Example Way, Example City, NY 10001")).toHaveLength(2);
    expect(screen.getAllByText("Maintenance")).toHaveLength(2);
    expect(screen.getByText("Job JOB-SYNTH-01")).toBeOnTheScreen();
    expect(screen.getByText("Appointment APT-SYNTH-02")).toBeOnTheScreen();
  });

  it("renders a legitimate empty day distinctly", async () => {
    const h = harness(day([]));
    render(<MyDayScreen service={h.service} network={h.network} />);
    expect(await screen.findByText("No work is currently assigned to you today.")).toBeOnTheScreen();
  });

  it.each([
    ["forbidden", /not available for your account/i],
    ["not_ready", /account is not ready/i],
    ["unauthenticated", /session has expired/i],
    ["malformed_response", /Unable to load My Day/i],
    ["unavailable", /Unable to load My Day/i],
  ] as const)("keeps %s failure distinct from empty", async (kind, expected) => {
    const h = harness();
    (h.service.day as jest.Mock).mockRejectedValue(new ApiFailure(kind, kind));
    render(<MyDayScreen service={h.service} network={h.network} />);
    expect(await screen.findByText(expected)).toBeOnTheScreen();
    expect(screen.queryByText(/No work is currently assigned/)).not.toBeOnTheScreen();
  });

  it("marks in-memory data stale offline and refreshes on restoration", async () => {
    const h = harness();
    render(<MyDayScreen service={h.service} network={h.network} />);
    await screen.findByText("Synthetic Customer One");
    h.setConnected(false);
    expect(await screen.findByText(/last confirmed and may be stale/i)).toBeOnTheScreen();
    expect(screen.getAllByLabelText(/^Open assignment detail.*stale/)).toHaveLength(2);
    h.setResult(day([second]));
    h.setConnected(true);
    await waitFor(() => expect(screen.queryByText("Synthetic Customer One")).not.toBeOnTheScreen());
    expect(screen.getByText("Synthetic Customer Two")).toBeOnTheScreen();
  });

  it("does not interpret initial offline state as an empty schedule", async () => {
    const h = harness(day([]), false);
    render(<MyDayScreen service={h.service} network={h.network} />);
    expect(await screen.findByText(/Connect to load your assigned work/i)).toBeOnTheScreen();
    expect(h.service.day).not.toHaveBeenCalled();
    expect(screen.queryByText(/No work is currently assigned/)).not.toBeOnTheScreen();
  });

  it("removes reassigned, removed-crew, and rescheduled work after authoritative refresh", async () => {
    const h = harness();
    render(<MyDayScreen service={h.service} network={h.network} />);
    await screen.findByText("Synthetic Customer One");
    h.setResult(day([]));
    await act(async () => screen.getByTestId("my-day-scroll").props.refreshControl.props.onRefresh());
    await waitFor(() => expect(screen.queryByText("Synthetic Customer One")).not.toBeOnTheScreen());
    expect(screen.getByText(/No work is currently assigned/)).toBeOnTheScreen();
  });

  it("renders cancellation only when retained by the projection", async () => {
    const h = harness(day([{ ...first, appointment_status: "cancelled" }]));
    render(<MyDayScreen service={h.service} network={h.network} />);
    expect(await screen.findByText(/cancelled · Primary assignment/)).toBeOnTheScreen();
    h.setResult(day([]));
    await act(async () => screen.getByTestId("my-day-scroll").props.refreshControl.props.onRefresh());
    await waitFor(() => expect(screen.queryByText(/cancelled · Primary assignment/)).not.toBeOnTheScreen());
  });

  it("never fabricates current or next from order, device time, or Workday state", async () => {
    const h = harness();
    render(<MyDayScreen service={h.service} network={h.network} />);
    await screen.findByText("Synthetic Customer One");
    expect(screen.queryByText(/CURRENT|NEXT/)).not.toBeOnTheScreen();
    expect(JSON.stringify(h.service)).not.toMatch(/punch|clock|startJob|finishJob/i);
  });

  it("provides card and refresh accessibility semantics", async () => {
    const h = harness();
    render(<MyDayScreen service={h.service} network={h.network} />);
    expect((await screen.findByLabelText(/Open assignment detail.*Synthetic Customer One/)).props.accessibilityRole).toBe("button");
    expect(screen.getByTestId("my-day-scroll").props.refreshControl.props.accessibilityLabel).toBe("Refresh authoritative assigned work");
  });

  it("accepts only the employee-safe strict projection", () => {
    const unsafe = { ...first, customer_phone: "555-0100", invoice_total: 100, compensation: 50, internal_notes: "private" };
    expect(dayAssignmentSchema.safeParse(unsafe).success).toBe(false);
    expect(JSON.stringify(first)).not.toMatch(/phone|email|invoice|payment|balance|cost|margin|payroll|compensation|note|problem|description/i);
  });

  it("calls only the self-service endpoint without identity or broad query parameters", async () => {
    const request = jest.fn(async (...args: unknown[]) => { void args; return day(); });
    await createEmployeeOperationsService({ request } as never).day();
    expect(request).toHaveBeenCalledWith("/api/v1/employee-operations/me/day", expect.anything());
    const [path, , init] = request.mock.calls[0] ?? [];
    expect(`${path}${JSON.stringify(init)}`).not.toMatch(/employee_id|jobs|scheduling|dispatch|customer/);
  });
});
