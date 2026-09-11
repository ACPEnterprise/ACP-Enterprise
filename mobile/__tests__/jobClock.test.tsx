import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import { JobClockPanel } from "../src/components/JobClockPanel";
import type { ActiveJobClock, JobClockAction, TimekeepingService } from "../src/api/timekeeping";
import { ApiFailure } from "../src/api/types";

jest.mock("expo-crypto", () => ({ randomUUID: jest.fn(() => "opaque-job-clock-key") }));
const jobId = "40000000-0000-4000-8000-000000000001";
const appointmentId = "30000000-0000-4000-8000-000000000001";
const inactive: ActiveJobClock = { active: false, event_id: null, employee_id: "synthetic-employee", job_id: null, appointment_id: null, started_at: null, server_observed_at: "2026-09-11T01:00:00Z", elapsed_seconds: null };
const active: ActiveJobClock = { active: true, event_id: "synthetic-event", employee_id: "synthetic-employee", job_id: jobId, appointment_id: appointmentId, started_at: "2026-09-11T01:00:00Z", server_observed_at: "2026-09-11T01:01:00Z", elapsed_seconds: 60 };

function harness(initial = inactive, connected = true) {
  let current = initial; let listener: ((value: boolean) => void) | undefined;
  const service: TimekeepingService = {
    state: jest.fn(), timecard: jest.fn(), punch: jest.fn(), jobClockState: jest.fn(async () => current),
    jobClock: jest.fn(async (action: JobClockAction) => { current = action === "start" ? active : inactive; return { event_id: "result-event", action, occurred_at: "2026-09-11T01:00:00Z", state: current, completed_interval: null }; }),
  };
  const network = { isConnected: jest.fn(async () => connected), subscribe: jest.fn((next: (value: boolean) => void) => { listener = next; return () => undefined; }) };
  return { service, network, setCurrent(value: ActiveJobClock) { current = value; }, reconnect(value: boolean) { connected = value; listener?.(value); } };
}

describe("authoritative Employee Job clock", () => {
  it("clocks onto the assigned Job without client Employee identity or timestamp", async () => {
    const h = harness(); render(<JobClockPanel service={h.service} network={h.network} jobId={jobId} appointmentId={appointmentId} enabled />);
    fireEvent.press(await screen.findByText("Clock On To This Job"));
    await waitFor(() => expect(h.service.jobClock).toHaveBeenCalledWith("start", jobId, appointmentId, "opaque-job-clock-key"));
    expect(JSON.stringify((h.service.jobClock as jest.Mock).mock.calls)).not.toMatch(/employee|occurred_at|timestamp/);
    expect(await screen.findByText("Clocked onto this Job")).toBeOnTheScreen();
  });

  it("clocks off the active assigned Job and returns to server-confirmed inactive state", async () => {
    const h = harness(active); render(<JobClockPanel service={h.service} network={h.network} jobId={jobId} appointmentId={appointmentId} enabled />);
    fireEvent.press(await screen.findByText("Clock Off This Job"));
    await waitFor(() => expect(h.service.jobClock).toHaveBeenCalledWith("stop", jobId, appointmentId, "opaque-job-clock-key"));
    expect(await screen.findByText("Not clocked onto a Job")).toBeOnTheScreen();
  });

  it("prevents duplicate taps while server confirmation is pending", async () => {
    const h = harness(); let finish!: () => void;
    (h.service.jobClock as jest.Mock).mockImplementation(() => new Promise((resolve) => { finish = () => resolve({ event_id: "result", action: "start", occurred_at: "2026-09-11T01:00:00Z", state: active, completed_interval: null }); }));
    render(<JobClockPanel service={h.service} network={h.network} jobId={jobId} appointmentId={appointmentId} enabled />);
    const button = await screen.findByText("Clock On To This Job"); fireEvent.press(button); fireEvent.press(button);
    await waitFor(() => expect(h.service.jobClock).toHaveBeenCalledTimes(1)); await act(async () => finish());
  });

  it("recovers a committed clock-on after the response is lost", async () => {
    const h = harness(); (h.service.jobClock as jest.Mock).mockImplementationOnce(async () => { h.setCurrent(active); throw new ApiFailure("timeout", "lost response"); });
    render(<JobClockPanel service={h.service} network={h.network} jobId={jobId} appointmentId={appointmentId} enabled />);
    fireEvent.press(await screen.findByText("Clock On To This Job"));
    expect(await screen.findByText("The latest Job clock confirms the action.")).toBeOnTheScreen();
    expect(screen.getByText("Clock Off This Job")).toBeEnabled();
  });

  it("reuses one logical request identity when an uncertain action is retried", async () => {
    const h = harness(); (h.service.jobClock as jest.Mock).mockRejectedValueOnce(new ApiFailure("timeout", "lost response"));
    render(<JobClockPanel service={h.service} network={h.network} jobId={jobId} appointmentId={appointmentId} enabled />);
    fireEvent.press(await screen.findByText("Clock On To This Job"));
    expect(await screen.findByText(/not confirmed/)).toBeOnTheScreen(); fireEvent.press(screen.getByText("Clock On To This Job"));
    await waitFor(() => expect(h.service.jobClock).toHaveBeenCalledTimes(2));
    expect((h.service.jobClock as jest.Mock).mock.calls[0][3]).toBe((h.service.jobClock as jest.Mock).mock.calls[1][3]);
  });

  it("fails closed offline and refreshes on reconnect", async () => {
    const h = harness(inactive, false); render(<JobClockPanel service={h.service} network={h.network} jobId={jobId} appointmentId={appointmentId} enabled />);
    expect(await screen.findByText(/offline/i)).toBeOnTheScreen(); expect(h.service.jobClock).not.toHaveBeenCalled();
    h.reconnect(true); await waitFor(() => expect(h.service.jobClockState).toHaveBeenCalled());
  });

  it("does not offer a contradictory start while another Job is active", async () => {
    const h = harness({ ...active, job_id: "40000000-0000-4000-8000-000000000099" }); render(<JobClockPanel service={h.service} network={h.network} jobId={jobId} appointmentId={appointmentId} enabled />);
    expect(await screen.findByText("Clocked onto another Job")).toBeOnTheScreen(); expect(screen.queryByText(/Clock On To This Job|Clock Off This Job/)).not.toBeOnTheScreen();
  });

  it("fails closed when assignment or own-punch authority is revoked", async () => {
    const h = harness(); (h.service.jobClockState as jest.Mock).mockRejectedValue(new ApiFailure("forbidden", "revoked"));
    render(<JobClockPanel service={h.service} network={h.network} jobId={jobId} appointmentId={appointmentId} enabled />);
    expect(await screen.findByText(/not available for your account/i)).toBeOnTheScreen();
    expect(screen.queryByText(/Clock On To This Job|Clock Off This Job/)).not.toBeOnTheScreen();
  });
});
