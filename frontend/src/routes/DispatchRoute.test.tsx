import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useDispatchBoard } from "../hooks/useDispatch";
import { useJobs } from "../hooks/useJobs";
import { DispatchRoute } from "./DispatchRoute";

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
}));
vi.mock("../hooks/useJobs");
vi.mock("../hooks/useDispatch", () => ({
  useDispatchBoard: vi.fn(),
  useEligibleTechnicians: vi.fn(),
  useDispatchMutations: vi.fn(),
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
    vi.clearAllMocks();
    vi.mocked(useDispatchBoard).mockReturnValue({
      isLoading: false,
      error: null,
      data: { items: [work], total_count: 1 },
      refetch: refetchDispatch,
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
    expect(
      screen.getByRole("button", { name: "Assign technician" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "JOB-000001" })).toHaveAttribute(
      "href",
      "/jobs/job-1",
    );
    expect(
      screen.queryByText("Technician assignment unavailable"),
    ).not.toBeInTheDocument();
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
    );
    expect(useJobs).toHaveBeenLastCalledWith(
      expect.objectContaining({ branchId: "branch-2" }),
    );
    const first = vi.mocked(useDispatchBoard).mock.calls[0][0];
    fireEvent.click(screen.getByRole("button", { name: "Next day" }));
    expect(vi.mocked(useDispatchBoard).mock.calls.at(-1)?.[0]).not.toBe(first);
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
});
