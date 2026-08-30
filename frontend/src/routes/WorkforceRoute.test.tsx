import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import * as workforceHooks from "../hooks/useWorkforce";
import { WorkforceRoute } from "./WorkforceRoute";

vi.mock("../hooks/useWorkforce");

const summary = {
  employee_id: "employee-1", employee_number: "EMP-1", display_name: "Marisol Rivera",
  job_title: "Service Technician", employee_type: "employee", employee_status: "active",
  home_branch_id: "branch-1", profile_id: "profile-1", profile_status: "active",
  technician: true, capability_codes: ["technician", "water_heater"], language_codes: ["en", "es"],
  readiness_state: "READY" as const, readiness_blockers: [], updated_at: "2026-08-30T12:00:00Z",
};

describe("WorkforceRoute", () => {
  function mockEligibility() {
    vi.mocked(workforceHooks.useWorkforceEligibility).mockReturnValue({
      isPending: false,
      isError: false,
      data: undefined,
      mutate: vi.fn(),
    } as never);
  }

  it("provides a visible operational profile without Payroll data", async () => {
    mockEligibility();
    vi.mocked(workforceHooks.useWorkforceDirectory).mockReturnValue({ isLoading: false, isError: false, isSuccess: true, data: [summary] } as never);
    vi.mocked(workforceHooks.useWorkforceEmployee).mockImplementation((id) => ({
      isLoading: false, isError: false,
      data: id ? { ...summary, capabilities: [{ code: "technician", display_name: "Technician", proficiency: "qualified", status: "active" }], certifications: [{ code: "trade", display_name: "Trade credential", credential_reference: "SAFE-REF", status: "active", issued_on: "2026-01-01", expires_on: "2027-01-01" }], languages: [{ code: "es", english_name: "Spanish", native_name: "Español", spoken_proficiency: "professional", customer_facing_eligible: true, interpreter_verified: false, status: "active" }], branches: [{ branch_id: "branch-1", status: "active", starts_on: null, ends_on: null }], work_restrictions: [], equipment_capabilities: [], availability: [] } : undefined,
    } as never));
    render(<WorkforceRoute />);
    await userEvent.click(screen.getByRole("button", { name: /Marisol Rivera/ }));
    expect(screen.getByRole("heading", { name: "Marisol Rivera" })).toBeInTheDocument();
    expect(screen.getByText("Spanish")).toBeInTheDocument();
    expect(screen.getByText((_, node) => node?.tagName === "P" && node.textContent?.includes("professional") === true)).toBeInTheDocument();
    expect(screen.getByText(/Trade credential/)).toBeInTheDocument();
    expect(screen.queryByText(/compensation|net pay|tax election/i)).not.toBeInTheDocument();
  });

  it("filters by explicit capability evidence", async () => {
    mockEligibility();
    vi.mocked(workforceHooks.useWorkforceDirectory).mockReturnValue({ isLoading: false, isError: false, isSuccess: true, data: [summary] } as never);
    vi.mocked(workforceHooks.useWorkforceEmployee).mockReturnValue({ isLoading: false, isError: false, data: undefined } as never);
    render(<WorkforceRoute />);
    await userEvent.type(screen.getByRole("textbox", { name: "Search workforce" }), "water_heater");
    expect(screen.getByText("Marisol Rivera")).toBeInTheDocument();
  });
});
