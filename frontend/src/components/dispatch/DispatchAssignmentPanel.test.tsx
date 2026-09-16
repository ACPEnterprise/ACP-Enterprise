import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { useDispatchMutations, useEligibleTechnicians } from "../../hooks/useDispatch";
import type { DispatchBoardItem } from "../../types/dispatch";
import { DispatchAssignmentPanel } from "./DispatchAssignmentPanel";

vi.mock("../../hooks/useDispatch");

const mutations = {
  assign: { isPending: false, error: null, mutate: vi.fn() },
  release: { isPending: false, error: null, mutate: vi.fn() },
  crew: { isPending: false, error: null, mutate: vi.fn() },
  reconcile: { isPending: false, error: null, mutate: vi.fn() },
  exception: { isPending: false, error: null, mutate: vi.fn() },
};

const released = {
  appointment_id: "appointment-1",
  appointment_number: "APT-1",
  job_id: "job-1",
  branch_id: "branch-1",
  status: "scheduled",
  window_start_at: "2026-09-17T13:00:00Z",
  window_end_at: "2026-09-17T15:00:00Z",
  assignment: {
    id: "assignment-1",
    appointment_id: "appointment-1",
    appointment_number: "APT-1",
    job_id: "job-1",
    company_id: "company-1",
    branch_id: "branch-1",
    primary_employee_id: "employee-1",
    primary_employee_name: "Former Technician",
    status: "released",
    arrival_state: "pending",
    active_exception_code: null,
    assignment_reason: "Released by dispatcher",
    window_start_at: "2026-09-17T13:00:00Z",
    window_end_at: "2026-09-17T15:00:00Z",
    effective_at: "2026-09-16T12:00:00Z",
    released_at: "2026-09-16T13:00:00Z",
    version: 2,
    crew_members: [{ id: "crew-1", employee_id: "employee-2", display_name: "Former Crew", status: "active", added_at: "2026-09-16T12:00:00Z" }],
  },
} as const satisfies DispatchBoardItem;

describe("DispatchAssignmentPanel", () => {
  it("treats terminal assignment evidence as history rather than active controls", () => {
    vi.mocked(useDispatchMutations).mockReturnValue(mutations as never);
    vi.mocked(useEligibleTechnicians).mockReturnValue({ isLoading: false, data: [] } as never);
    render(<MemoryRouter><DispatchAssignmentPanel item={released} onClose={vi.fn()} /></MemoryRouter>);

    expect(screen.getByText(/No primary technician/)).toBeVisible();
    expect(screen.getByText((_, element) => element?.textContent === "The latest assignment is released history. Assign a technician to create new current Dispatch authority.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Assign primary" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Add crew member" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Release assignment" })).not.toBeInTheDocument();
    expect(screen.queryByText("Former Crew")).not.toBeInTheDocument();
  });
});
