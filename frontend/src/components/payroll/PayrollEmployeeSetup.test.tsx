import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { usePayrollEmployeeSetup } from "../../hooks/usePayroll";
import { PayrollEmployeeSetup } from "./PayrollEmployeeSetup";

vi.mock("../../auth", () => ({ useHasPermission: () => true }));
vi.mock("../../hooks/usePayroll", () => ({ usePayrollEmployeeSetup: vi.fn() }));
vi.mock("../../api/payroll", () => ({ draftPayrollInput: vi.fn() }));

describe("PayrollEmployeeSetup", () => {
  it("shows exact blockers and never substitutes zero", () => {
    vi.mocked(usePayrollEmployeeSetup).mockReturnValue({
      query: { isPending: false, isError: false, data: {
        employee_id: "employee-1", employee_name: "Synthetic Employee", employee_number: "EMP-1",
        readiness: "BLOCKED_FOR_PAYROLL", blockers: ["tax:federal_withholding_election:missing"],
        protected_input_configuration_ready: false, compensations: [], inputs: [],
      } },
      draftCompensation: { mutateAsync: vi.fn() },
      approveCompensation: { mutate: vi.fn() }, approveInput: { mutate: vi.fn() },
    } as never);
    render(<PayrollEmployeeSetup employeeId="employee-1" />);
    expect(screen.getByText("BLOCKED_FOR_PAYROLL")).toBeVisible();
    expect(screen.getByText(/federal withholding election · missing/i)).toBeVisible();
    expect(screen.getAllByText(/not zero/i).length).toBeGreaterThan(0);
    expect(screen.queryByText("0.00")).not.toBeInTheDocument();
    expect(screen.getByText(/encryption keyring/i)).toBeVisible();
  });
});
