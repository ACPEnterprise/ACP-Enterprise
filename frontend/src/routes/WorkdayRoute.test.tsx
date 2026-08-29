import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, AxiosHeaders } from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as workdayApi from "../api/timekeeping";
import { AuthenticationContext, type AuthenticationContextValue } from "../auth/AuthenticationContext";
import { WorkdayRoute } from "./WorkdayRoute";

vi.mock("../api/timekeeping", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/timekeeping")>();
  return {
    ...original,
    getOwnPunchState: vi.fn(),
    getOwnTimecard: vi.fn(),
    recordOwnPunch: vi.fn(),
  };
});

const state = (value: workdayApi.WorkdayStateName): workdayApi.PunchState => ({
  state: value,
  last_action: value === "not_clocked_in" ? "clock_out" : value === "on_break" ? "break_start" : "clock_in",
  occurred_at: value === "not_clocked_in" ? null : "2026-08-28T13:00:00Z",
  server_observed_at: "2026-08-28T14:00:00Z",
  elapsed_seconds: value === "not_clocked_in" ? null : 3600,
});

const entry = (overrides: Partial<workdayApi.TimeEntry> = {}): workdayApi.TimeEntry => ({
  entry_id: "entry-1",
  revision_id: "revision-1",
  revision_number: 1,
  work_date: "2026-08-28",
  timezone: "America/New_York",
  provenance: "employee_punch",
  start_at: "2026-08-28T13:00:00Z",
  end_at: "2026-08-28T14:00:00Z",
  approved_duration_minutes: 60,
  state: "approved",
  supersedes_revision_id: null,
  correction_reason: null,
  approved_at: "2026-08-28T15:00:00Z",
  ...overrides,
});

const timecard = (entries: workdayApi.TimeEntry[] = []): workdayApi.Timecard => ({
  employee_id: "employee-1",
  punch_state: state("not_clocked_in"),
  pay_period: {
    id: "period-1",
    period_start: "2026-08-22",
    period_end: "2026-08-28",
    processing_date: "2026-09-03",
    payday: "2026-09-04",
    timezone: "America/New_York",
    schedule_definition_id: "weekly",
    schedule_version: 1,
  },
  entries,
});

const auth = (permissions = ["COMPANY_TIMEKEEPING_OWN_READ", "COMPANY_TIMEKEEPING_OWN_PUNCH"]): AuthenticationContextValue => ({
  status: "authenticated",
  user: { id: "user", normalized_email: "masked@example.test", first_name: "Synthetic", last_name: "Employee", display_name: "Synthetic Employee", email_verified_at: "2026-08-28T00:00:00Z" },
  activeCompany: {
    id: "company",
    name: "Synthetic Company",
    code: "SYN",
    membership_id: "membership",
    default_branch_id: "branch",
    has_all_branch_access: false,
    branches: [{ id: "branch", code: "MAIN", name: "Main", is_primary: true }],
  },
  permissionCodes: permissions,
  signIn: vi.fn(),
  signOut: vi.fn(),
  signOutAll: vi.fn(),
  requireReauthentication: vi.fn(),
});

function renderWorkday(context = auth()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <AuthenticationContext.Provider value={context}>
      <QueryClientProvider client={client}><WorkdayRoute /></QueryClientProvider>
    </AuthenticationContext.Provider>,
  );
}

beforeEach(() => {
  vi.mocked(workdayApi.getOwnPunchState).mockReset().mockResolvedValue(state("not_clocked_in"));
  vi.mocked(workdayApi.getOwnTimecard).mockReset().mockResolvedValue(timecard());
  vi.mocked(workdayApi.recordOwnPunch).mockReset().mockImplementation(async (action) => ({
    punch_id: "punch-1",
    action,
    occurred_at: "2026-08-28T14:00:00Z",
    state: action === "clock_in" ? state("clocked_in") : state("not_clocked_in"),
    completed_entry: null,
  }));
});

describe("mobile Workday Time route", () => {
  it.each([
    ["not_clocked_in", ["Clock In"], ["Start Break", "End Break", "Clock Out"]],
    ["clocked_in", ["Start Break", "Clock Out"], ["Clock In", "End Break"]],
    ["on_break", ["End Break"], ["Clock In", "Start Break", "Clock Out"]],
  ] as const)("offers only valid actions while %s", async (value, offered, absent) => {
    vi.mocked(workdayApi.getOwnPunchState).mockResolvedValue(state(value));
    renderWorkday();
    for (const label of offered) expect(await screen.findByRole("button", { name: label })).toBeInTheDocument();
    for (const label of absent) expect(screen.queryByRole("button", { name: label })).not.toBeInTheDocument();
  });

  it("blocks duplicate taps while one punch is pending", async () => {
    let complete!: (value: workdayApi.PunchResult) => void;
    vi.mocked(workdayApi.recordOwnPunch).mockReturnValue(new Promise((resolve) => { complete = resolve; }));
    renderWorkday();
    const button = await screen.findByRole("button", { name: "Clock In" });
    fireEvent.click(button);
    fireEvent.click(button);
    await waitFor(() => expect(workdayApi.recordOwnPunch).toHaveBeenCalledTimes(1));
    complete({ punch_id: "punch", action: "clock_in", occurred_at: "2026-08-28T14:00:00Z", state: state("clocked_in"), completed_entry: null });
    expect(await screen.findByText("Punch accepted")).toBeInTheDocument();
  });

  it("reconciles an uncertain network outcome to authoritative server state", async () => {
    vi.mocked(workdayApi.getOwnPunchState)
      .mockResolvedValueOnce(state("not_clocked_in"))
      .mockResolvedValue(state("clocked_in"));
    vi.mocked(workdayApi.recordOwnPunch).mockRejectedValue(new AxiosError("Network unavailable"));
    renderWorkday();
    await userEvent.click(await screen.findByRole("button", { name: "Clock In" }));
    expect(await screen.findByText("Confirming server state")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Clocked in" })).toBeInTheDocument();
  });

  it("shows manual and corrected provenance without exposing compensation", async () => {
    vi.mocked(workdayApi.getOwnTimecard).mockResolvedValue(timecard([
      entry({ revision_id: "manual", provenance: "authorized_manual_entry" }),
      entry({ revision_id: "corrected", revision_number: 2, supersedes_revision_id: "original", correction_reason: "Missed punch" }),
    ]));
    renderWorkday();
    expect(await screen.findByText("Manager-entered time")).toBeInTheDocument();
    expect(screen.getByText("Corrected entry")).toBeInTheDocument();
    expect(screen.getByText("Correction noted: Missed punch")).toBeInTheDocument();
    expect(screen.queryByText(/salary|pay rate|compensation|tax|payroll total/i)).not.toBeInTheDocument();
    expect(screen.getByText(/contact an authorized manager/i)).toBeInTheDocument();
  });

  it("fails safely when permission or Employee linkage is missing", async () => {
    const denied = renderWorkday(auth([]));
    expect(screen.getByText("Timekeeping access is unavailable")).toBeInTheDocument();
    expect(workdayApi.getOwnPunchState).not.toHaveBeenCalled();
    denied.unmount();

    const config = { headers: new AxiosHeaders() };
    vi.mocked(workdayApi.getOwnPunchState).mockRejectedValue(new AxiosError("Missing Employee", "ERR_BAD_RESPONSE", undefined, undefined, {
      data: { detail: "Employee self-resolution is unavailable." },
      status: 422,
      statusText: "Unprocessable Entity",
      headers: new AxiosHeaders(),
      config: config as never,
    }));
    renderWorkday();
    expect(await screen.findByText("Onboarding is incomplete")).toBeInTheDocument();
  });

  it("handles session invalidation and renders phone-safe touch controls", async () => {
    vi.mocked(workdayApi.getOwnPunchState).mockRejectedValue(new AxiosError("Unauthorized", "ERR_BAD_RESPONSE", undefined, undefined, {
      data: {}, status: 401, statusText: "Unauthorized", headers: new AxiosHeaders(), config: { headers: new AxiosHeaders() } as never,
    }));
    const view = renderWorkday();
    expect(await screen.findByText("Sign in again")).toBeInTheDocument();
    view.unmount();

    vi.mocked(workdayApi.getOwnPunchState).mockResolvedValue(state("not_clocked_in"));
    renderWorkday();
    const button = await screen.findByRole("button", { name: "Clock In" });
    expect(button).toHaveClass("min-h-14");
    expect(screen.getByText(/phone does not determine payable duration/i)).toBeInTheDocument();
    await waitFor(() => expect(workdayApi.getOwnTimecard).toHaveBeenCalled());
  });

  it("rehydrates after foregrounding and keeps salaried attendance free of wage meaning", async () => {
    renderWorkday();
    await screen.findByRole("heading", { name: "Clocked out" });
    expect(workdayApi.getOwnPunchState).toHaveBeenCalledTimes(1);
    window.dispatchEvent(new Event("focus"));
    await waitFor(() => expect(workdayApi.getOwnPunchState).toHaveBeenCalledTimes(2));
    expect(screen.queryByText(/salary|hourly rate|wages|overtime|compensation/i)).not.toBeInTheDocument();
  });
});
