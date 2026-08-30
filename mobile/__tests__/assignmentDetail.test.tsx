import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import { Linking } from "react-native";
import type { DayAssignment, EmployeeDay, EmployeeOperationsService } from "../src/api/employeeOperations";
import type { FieldService } from "../src/api/fieldService";
import { ApiFailure } from "../src/api/types";
import { directionsUrl, JobWorkspaceScreen } from "../src/screens/JobWorkspaceScreen";
import { MyDayScreen } from "../src/screens/MyDayScreen";

const assignment: DayAssignment = {
  appointment_id: "30000000-0000-4000-8000-000000000001",
  appointment_number: "APT-SAFE-01",
  appointment_status: "scheduled",
  job_id: "40000000-0000-4000-8000-000000000001",
  job_number: "JOB-SAFE-01",
  job_status: "open",
  service_category: "Inspection",
  window_start_at: "2026-08-28T13:00:00Z",
  window_end_at: "2026-08-28T15:00:00Z",
  assignment_role: "primary",
  assignment_status: "assigned",
  designation: null,
  customer_display_name: "Synthetic Detail Customer",
  service_location: { label: "Synthetic Detail Site", address_line_1: "200 Example Avenue", address_line_2: "Unit 2", city: "Example City", state: "NY", postal_code: "10002", country: "US" },
};
const projectedDay = (assignments: DayAssignment[] = [assignment]): EmployeeDay => ({ business_date: "2026-08-28", timezone: "America/New_York", assignments });
const fieldService: FieldService = {
  itinerary: jest.fn(), state: jest.fn(), arrival: jest.fn(), note: jest.fn(), approval: jest.fn(), refreshHandoff: jest.fn(),
};

function harness(initial = projectedDay(), connected = true) {
  let value = initial;
  let listener: ((connected: boolean) => void) | undefined;
  const service: EmployeeOperationsService = { day: jest.fn(async () => value) };
  const network = { isConnected: jest.fn(async () => connected), subscribe: jest.fn((next: (connected: boolean) => void) => { listener = next; return () => undefined; }) };
  return { service, network, replace(next: EmployeeDay) { value = next; }, connect(next: boolean) { connected = next; act(() => listener?.(next)); } };
}

function detail(h: ReturnType<typeof harness>, appointmentId = assignment.appointment_id, initial: DayAssignment | null = assignment) {
  return <JobWorkspaceScreen appointmentId={appointmentId} initialAssignment={initial} initialTimezone="America/New_York" service={h.service} fieldService={fieldService} network={h.network} />;
}

describe("native employee Job workspace", () => {
  afterEach(() => jest.restoreAllMocks());
  it("opens an own-assignment detail from My Day", async () => {
    const h = harness(); const open = jest.fn();
    render(<MyDayScreen service={h.service} network={h.network} onOpenAssignment={open} />);
    fireEvent.press(await screen.findByLabelText(/Open assignment detail.*Synthetic Detail Customer/));
    expect(open).toHaveBeenCalledWith(assignment, "America/New_York", "2026-08-28");
  });

  it("renders only safe operational detail with accessible hierarchy", async () => {
    const h = harness(); render(detail(h));
    expect(await screen.findByText("Synthetic Detail Customer")).toBeOnTheScreen();
    expect(screen.getByText("200 Example Avenue")).toBeOnTheScreen();
    expect(screen.getByText("Unit 2")).toBeOnTheScreen();
    expect(screen.getByText("Inspection")).toBeOnTheScreen();
    expect(screen.getByText("Appointment APT-SAFE-01")).toBeOnTheScreen();
    expect(screen.getByText("Job JOB-SAFE-01")).toBeOnTheScreen();
    expect(screen.getByLabelText(/Authoritative assignment detail.*Synthetic Detail Customer/)).toBeOnTheScreen();
    expect(screen.getByText("Read-only assigned work. Job status and My Time remain independent.")).toBeOnTheScreen();
    expect(screen.getByTestId("job-workspace-scroll").props.refreshControl.props.accessibilityLabel).toBe("Refresh authoritative Job workspace");
  });

  it("fails closed for guessed, cross-Company, or cross-Branch identifiers", async () => {
    const h = harness();
    render(detail(h, "90000000-0000-4000-8000-000000000009", null));
    expect(await screen.findByText(/no longer available in your authoritative My Day/i)).toBeOnTheScreen();
    expect(screen.queryByText("Synthetic Detail Customer")).not.toBeOnTheScreen();
    expect(h.service.day).toHaveBeenCalledTimes(1);
  });

  it("invalidates access after reassignment or crew removal refresh", async () => {
    const h = harness(); render(detail(h));
    await screen.findByText("Synthetic Detail Customer");
    h.replace(projectedDay([]));
    await act(async () => screen.getByTestId("job-workspace-scroll").props.refreshControl.props.onRefresh());
    await waitFor(() => expect(screen.queryByText("Synthetic Detail Customer")).not.toBeOnTheScreen());
    expect(screen.getByText(/no longer available/i)).toBeOnTheScreen();
  });

  it("reflects authoritative cancellation and rescheduling", async () => {
    const h = harness(); render(detail(h)); await screen.findByText("Synthetic Detail Customer");
    h.replace(projectedDay([{ ...assignment, appointment_status: "cancelled" }]));
    await act(async () => screen.getByTestId("job-workspace-scroll").props.refreshControl.props.onRefresh());
    expect(await screen.findByText("Appointment status: cancelled")).toBeOnTheScreen();
    h.replace(projectedDay([]));
    await act(async () => screen.getByTestId("job-workspace-scroll").props.refreshControl.props.onRefresh());
    expect(await screen.findByText(/no longer available/i)).toBeOnTheScreen();
  });

  it("marks last-confirmed detail stale offline and refreshes on restoration", async () => {
    const h = harness(); render(detail(h)); await screen.findByText("Synthetic Detail Customer");
    h.connect(false);
    expect(await screen.findByText(/last confirmed and may be stale/i)).toBeOnTheScreen();
    expect(screen.getByLabelText(/Stale assignment detail/)).toBeOnTheScreen();
    h.replace(projectedDay([])); h.connect(true);
    expect(await screen.findByText(/no longer available/i)).toBeOnTheScreen();
  });

  it.each([
    ["unauthenticated", /session has expired/i],
    ["forbidden", /not authorized/i],
    ["not_ready", /account is not ready/i],
    ["malformed_response", /Unable to refresh/i],
    ["unavailable", /Unable to refresh/i],
  ] as const)("keeps %s distinct", async (kind, expected) => {
    const h = harness(); (h.service.day as jest.Mock).mockRejectedValue(new ApiFailure(kind, kind));
    render(detail(h)); expect(await screen.findByText(expected)).toBeOnTheScreen();
    if (["unauthenticated", "forbidden", "not_ready"].includes(kind)) expect(screen.queryByText("Synthetic Detail Customer")).not.toBeOnTheScreen();
  });

  it("contains no mutation, identity-selection, contact, financial, Payroll, or note surface", async () => {
    const h = harness(); render(detail(h)); await screen.findByText("Synthetic Detail Customer");
    expect(screen.queryByText(/Start Job|Finish Job|Arrive|Dispatch|Reassign|Cancel Job|Reschedule|Complete|Pause|employee_id/i)).not.toBeOnTheScreen();
    expect(screen.queryByText(/phone|email|estimate|invoice|payment|balance|margin|cost|payroll|compensation|note|description|customer history/i)).not.toBeOnTheScreen();
    expect(Object.keys(h.service)).toEqual(["day"]);
  });

  it("creates a bounded system-map handoff without location tracking", () => {
    expect(directionsUrl(assignment, "ios")).toBe("https://maps.apple.com/?daddr=Synthetic%20Detail%20Site%2C%20200%20Example%20Avenue%2C%20Unit%202%2C%20Example%20City%2C%20NY%2010002");
    expect(directionsUrl(assignment, "android")).toBe("geo:0,0?q=Synthetic%20Detail%20Site%2C%20200%20Example%20Avenue%2C%20Unit%202%2C%20Example%20City%2C%20NY%2010002");
  });

  it("opens directions only after an explicit employee action", async () => {
    const canOpen = jest.spyOn(Linking, "canOpenURL").mockResolvedValue(true);
    const open = jest.spyOn(Linking, "openURL").mockResolvedValue(undefined);
    const h = harness(); render(detail(h));
    fireEvent.press(await screen.findByLabelText("Open directions to Synthetic Detail Site"));
    await waitFor(() => expect(open).toHaveBeenCalledWith(expect.stringContaining("maps.apple.com")));
    expect(canOpen).toHaveBeenCalledTimes(1);
  });

  it("fails safely when no system map application is available", async () => {
    jest.spyOn(Linking, "canOpenURL").mockResolvedValue(false);
    const h = harness(); render(detail(h));
    fireEvent.press(await screen.findByLabelText("Open directions to Synthetic Detail Site"));
    expect(await screen.findByRole("alert", { name: /Directions are unavailable/i })).toBeOnTheScreen();
  });
});
