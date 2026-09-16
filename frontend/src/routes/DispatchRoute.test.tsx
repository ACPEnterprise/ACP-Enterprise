import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useDispatchBoard, useDispatchMutations, useDispatchRecommendation, useEligibleTechnicians } from "../hooks/useDispatch";
import { useJobs } from "../hooks/useJobs";
import { DispatchRoute } from "./DispatchRoute";

let permissions = new Set([
  "COMPANY_DISPATCH_READ",
  "COMPANY_DISPATCH_MANAGE",
  "COMPANY_JOB_READ",
]);
vi.mock("../auth", () => ({
  useAuth: () => ({
    activeCompany: {
      id: "company-1",
      branches: [
        { id: "branch-1", name: "Main", code: "MAIN" },
        { id: "branch-2", name: "North", code: "NORTH" },
      ],
    },
  }),
  useHasPermission: (code: string) => permissions.has(code),
}));
vi.mock("../hooks/useJobs");
vi.mock("../hooks/useDispatch", () => ({
  useDispatchBoard: vi.fn(),
  useEligibleTechnicians: vi.fn(),
  useDispatchMutations: vi.fn(),
  useDispatchRecommendation: vi.fn(),
}));
const refetchDispatch = vi.fn(),
  refetchJobs = vi.fn();
const work = {
  appointment_id: "appointment-1",
  appointment_number: "APT-000001",
  job_id: "job-1",
  branch_id: "branch-1",
  status: "scheduled",
  window_start_at: "2026-08-03T13:00:00Z",
  window_end_at: "2026-08-03T15:00:00Z",
  assignment: null,
};
const job = {
  id: "job-1",
  job_number: "JOB-000001",
  status: "paused",
  priority: "urgent",
  customer_display_name: "Taylor Home",
  service_location_label: "10 Main Street",
  earliest_appointment_start_at: null,
  updated_at: "2026-08-03T12:00:00Z",
};

describe("DispatchRoute", () => {
  beforeEach(() => {
    permissions = new Set([
      "COMPANY_DISPATCH_READ",
      "COMPANY_DISPATCH_MANAGE",
      "COMPANY_JOB_READ",
    ]);
    vi.clearAllMocks();
    vi.mocked(useDispatchBoard).mockReturnValue({
      isLoading: false,
      error: null,
      data: { items: [work], total_count: 1 },
      refetch: refetchDispatch,
    } as never);
    vi.mocked(useEligibleTechnicians).mockReturnValue({ isLoading: false, data: [] } as never);
    vi.mocked(useDispatchRecommendation).mockReturnValue({ isLoading: false, data: null } as never);
    vi.mocked(useDispatchMutations).mockReturnValue({
      assign: { isPending: false, error: null }, release: { isPending: false, error: null },
      crew: { isPending: false, error: null }, reconcile: { isPending: false, error: null },
      exception: { isPending: false, error: null },
    } as never);
    vi.mocked(useJobs).mockReturnValue({
      isLoading: false,
      error: null,
      data: { items: [job], total_count: 1, total_pages: 1 },
      refetch: refetchJobs,
    } as never);
  });
  it("renders durable assignment controls and operational Jobs", () => {
    render(
      <MemoryRouter>
        <DispatchRoute />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("heading", { name: "Dispatch" }),
    ).toBeInTheDocument();
    expect(screen.getByText("APT-000001")).toBeInTheDocument();
    expect(screen.getByText("Taylor Home · 10 Main Street")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Assign technician" }),
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole("link", { name: "JOB-000001" })[0],
    ).toHaveAttribute("href", "/jobs/job-1");
    expect(
      screen.queryByText("Technician assignment unavailable"),
    ).not.toBeInTheDocument();
  });
  it("supports bounded operator search and state filters", () => {
    render(
      <MemoryRouter>
        <DispatchRoute />
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByRole("textbox", { name: "Search Dispatch" }), {
      target: { value: "missing customer" },
    });
    expect(screen.getByText("No scheduled work")).toBeVisible();
    fireEvent.change(screen.getByRole("textbox", { name: "Search Dispatch" }), {
      target: { value: "Taylor" },
    });
    expect(screen.getByText("APT-000001")).toBeVisible();
    fireEvent.change(
      screen.getByRole("combobox", { name: "Dispatch operating state" }),
      {
        target: { value: "completed" },
      },
    );
    expect(screen.getByText("No scheduled work")).toBeVisible();
  });
  it("updates authoritative Dispatch scope", () => {
    render(
      <MemoryRouter>
        <DispatchRoute />
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByRole("combobox", { name: "Branch" }), {
      target: { value: "branch-2" },
    });
    expect(useDispatchBoard).toHaveBeenLastCalledWith(
      expect.any(String),
      expect.any(String),
      "branch-2",
      true,
    );
    expect(useJobs).toHaveBeenLastCalledWith(
      expect.objectContaining({ branchId: "branch-2" }),
      true,
    );
    const first = vi.mocked(useDispatchBoard).mock.calls[0][0];
    fireEvent.click(screen.getByRole("button", { name: "Next day" }));
    expect(vi.mocked(useDispatchBoard).mock.calls.at(-1)?.[0]).not.toBe(first);
  });
  it("disables Dispatch and Job queries without Dispatch read authority", () => {
    permissions = new Set();
    render(
      <MemoryRouter>
        <DispatchRoute />
      </MemoryRouter>,
    );
    expect(screen.getByText(/not authorized to view Dispatch/i)).toBeVisible();
    expect(useDispatchBoard).toHaveBeenCalledWith(
      expect.any(String),
      expect.any(String),
      undefined,
      false,
    );
    expect(useJobs).toHaveBeenCalledWith(expect.any(Object), false);
  });
  it("separates Dispatch read, manage, and Job read authority", () => {
    permissions = new Set(["COMPANY_DISPATCH_READ"]);
    render(
      <MemoryRouter>
        <DispatchRoute />
      </MemoryRouter>,
    );
    expect(screen.getByText("APT-000001")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Assign technician" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/Operational Jobs require Job read authority/i),
    ).toBeVisible();
    expect(useJobs).toHaveBeenCalledWith(expect.any(Object), false);
  });
  it("isolates a failed Dispatch board from Jobs", () => {
    vi.mocked(useDispatchBoard).mockReturnValue({
      isLoading: false,
      error: { isAxiosError: true, message: "Network Error" },
      data: undefined,
      refetch: refetchDispatch,
    } as never);
    render(
      <MemoryRouter>
        <DispatchRoute />
      </MemoryRouter>,
    );
    expect(screen.getByText("Dispatch board unavailable")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "JOB-000001" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(refetchDispatch).toHaveBeenCalled();
  });
  it("renders independent empty and loading states", () => {
    vi.mocked(useDispatchBoard).mockReturnValue({
      isLoading: true,
      error: null,
      data: undefined,
      refetch: refetchDispatch,
    } as never);
    vi.mocked(useJobs).mockReturnValue({
      isLoading: false,
      error: null,
      data: { items: [], total_count: 0, total_pages: 0 },
      refetch: refetchJobs,
    } as never);
    render(
      <MemoryRouter>
        <DispatchRoute />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("status", { name: "Loading Dispatch board" }),
    ).toBeInTheDocument();
    expect(screen.getByText("No operational Jobs")).toBeInTheDocument();
  });
  it("keeps assignment action reachable at iPhone width", () => {
    Object.defineProperty(window, "innerWidth", {
      value: 390,
      configurable: true,
    });
    render(
      <MemoryRouter>
        <DispatchRoute />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("button", { name: "Assign technician" }),
    ).toBeVisible();
  });

  it("shows authoritative arrival and exception state", () => {
    vi.mocked(useDispatchBoard).mockReturnValue({
      isLoading: false,
      error: null,
      data: {
        items: [
          {
            ...work,
            assignment: {
              id: "assignment-1",
              primary_employee_name: "Technician One",
              status: "reconciliation_required",
              arrival_state: "arrived",
              active_exception_code: "safety_condition",
              crew_members: [],
            },
          },
        ],
        total_count: 1,
      },
      refetch: refetchDispatch,
    } as never);
    render(
      <MemoryRouter>
        <DispatchRoute />
      </MemoryRouter>,
    );
    expect(
      screen.getByText(/reconciliation required · arrived/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Exception: safety condition/i),
    ).toBeInTheDocument();
  });

  it("reconciles the open assignment panel from refreshed board authority", () => {
    const rendered = render(<MemoryRouter><DispatchRoute /></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: "Assign technician" }));
    expect(screen.getByText(/No primary technician/)).toBeVisible();

    vi.mocked(useDispatchBoard).mockReturnValue({
      isLoading: false,
      error: null,
      data: { items: [{
        ...work,
        assignment: {
          id: "assignment-1", appointment_id: work.appointment_id,
          appointment_number: work.appointment_number, job_id: work.job_id,
          company_id: "company-1", branch_id: work.branch_id,
          primary_employee_id: "employee-1", primary_employee_name: "Technician One",
          status: "assigned", arrival_state: "pending", active_exception_code: null,
          assignment_reason: "Dispatcher assignment", window_start_at: work.window_start_at,
          window_end_at: work.window_end_at, effective_at: "2026-08-03T12:00:00Z",
          released_at: null, version: 1, crew_members: [],
        },
      }], total_count: 1 },
      refetch: refetchDispatch,
    } as never);
    rendered.rerender(<MemoryRouter><DispatchRoute /></MemoryRouter>);

    expect(screen.getAllByText(/Technician One/).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Replace primary" })).toBeVisible();
  });
});
