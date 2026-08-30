import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import type { EmployeeOperationsService } from "../src/api/employeeOperations";
import type { FieldService } from "../src/api/fieldService";
import { JobWorkspaceScreen } from "../src/screens/JobWorkspaceScreen";

const assignment = { appointment_id: "30000000-0000-4000-8000-000000000001", appointment_number: "APT-FIELD-01", appointment_status: "scheduled", job_id: "40000000-0000-4000-8000-000000000001", job_number: "JOB-FIELD-01", job_status: "open", service_category: "Synthetic service", window_start_at: "2026-08-28T23:30:00Z", window_end_at: "2026-08-29T01:00:00Z", assignment_role: "primary" as const, assignment_status: "assigned", designation: null, customer_display_name: "Synthetic Field Customer", service_location: { label: "Synthetic Field Site", address_line_1: "300 Fixture Lane", address_line_2: null, city: "Example", state: "NY", postal_code: "10001", country: "US" } };
function harness() {
  const employee: EmployeeOperationsService = { day: jest.fn(async () => ({ business_date: "2026-08-28", timezone: "America/New_York", assignments: [assignment] })) };
  const item = { appointment_id: assignment.appointment_id, appointment_number: assignment.appointment_number, job_id: assignment.job_id, job_number: assignment.job_number, job_status: "open", job_version: 2, customer_display_name: assignment.customer_display_name, service_location_label: "Synthetic Field Site", window_start_at: assignment.window_start_at, window_end_at: assignment.window_end_at, assignment_status: "assigned", assignment_version: 3, arrival_state: "pending" as const, field_execution_enabled: true };
  const field: FieldService = { itinerary: jest.fn(async () => ({ service_date: "2026-08-28", technician_display_name: "Synthetic Technician", items: [item] })), state: jest.fn(async () => ({ job_id: assignment.job_id!, assignment_id: "50000000-0000-4000-8000-000000000001", work_summary_recorded: false, customer_disposition: null, completion_ready: false, requirement_snapshot_version: null, missing_requirements: ["work_performed_summary"], commercial_authorization: "missing" as const, non_billable_reason: null, invoice_handoff_status: null, invoice_id: null })), arrival: jest.fn(async () => undefined), note: jest.fn(), approval: jest.fn(), refreshHandoff: jest.fn() };
  const network = { isConnected: jest.fn(async () => true), subscribe: jest.fn(() => () => undefined) };
  return { employee, field, network };
}

describe("authorized employee field workflow", () => {
  it("uses the authoritative business date and exposes accepted actions without Job lifecycle mutation", async () => {
    const h = harness(); render(<JobWorkspaceScreen appointmentId={assignment.appointment_id} initialAssignment={assignment} initialTimezone="America/New_York" businessDate="2026-08-28" service={h.employee} fieldService={h.field} network={h.network} canReadField canExecuteField />);
    expect(await screen.findByText("Travel status: pending")).toBeOnTheScreen();
    expect(h.field.itinerary).toHaveBeenCalledWith("2026-08-28");
    expect(screen.getByLabelText("Work performed summary")).toBeOnTheScreen();
    expect(screen.getByText(/Starting or completing the Job is not offered/)).toBeOnTheScreen();
    expect(screen.queryByText(/^Start Job$|^Complete Job$|^Finish Job$/)).not.toBeOnTheScreen();
  });

  it("prevents duplicate action while authoritative reconciliation is in flight", async () => {
    const h = harness(); let release!: () => void; (h.field.arrival as jest.Mock).mockImplementation(() => new Promise<void>((resolve) => { release = resolve; }));
    render(<JobWorkspaceScreen appointmentId={assignment.appointment_id} initialAssignment={assignment} initialTimezone="America/New_York" businessDate="2026-08-28" service={h.employee} fieldService={h.field} network={h.network} canReadField canExecuteField />);
    const action = await screen.findByRole("button", { name: "Begin Travel" }); fireEvent.press(action); fireEvent.press(action);
    await waitFor(() => expect(h.field.arrival).toHaveBeenCalledTimes(1)); expect(screen.getByRole("button", { name: "Begin Travel" }).props.accessibilityState.disabled).toBe(true);
    await act(async () => release()); await waitFor(() => expect(h.field.state).toHaveBeenCalledTimes(2));
  });
});
