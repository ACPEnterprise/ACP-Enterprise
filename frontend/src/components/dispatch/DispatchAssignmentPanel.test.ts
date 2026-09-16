import { describe, expect, it } from "vitest";

import type { TechnicianEligibility } from "../../types/dispatch";
import { dispatchReadiness, isDispatchSelectable } from "./dispatchEligibility";

const technician: TechnicianEligibility = {
  employee_id: "employee-field-tech",
  employee_number: "EMP-TEST",
  display_name: "Owner-confirmed Field Tech",
  branch_id: "branch-main",
  job_title: "Service Technician",
  capability_codes: ["technician"],
  language_codes: [],
  eligible: false,
  decision: "not_eligible",
  reasons: ["availability_unknown"],
  availability_confidence: "unknown",
};

describe("Dispatch technician selection", () => {
  it("does not promote Workforce readiness from the assignment panel", () => {
    expect(isDispatchSelectable(technician)).toBe(false);
    expect(isDispatchSelectable({ ...technician, eligible: true })).toBe(true);
  });
  it("projects canonical Workforce reasons into bounded readiness labels", () => {
    expect(dispatchReadiness(technician)).toBe("AVAILABILITY_NOT_READY");
    expect(
      dispatchReadiness({
        ...technician,
        reasons: ["missing_workforce_profile"],
      }),
    ).toBe("TECHNICIAN_NOT_READY");
    expect(
      dispatchReadiness({ ...technician, reasons: ["wrong_branch"] }),
    ).toBe("BRANCH_NOT_READY");
    expect(
      dispatchReadiness({
        ...technician,
        reasons: ["missing_required_capability"],
      }),
    ).toBe("CAPABILITY_NOT_READY");
    expect(dispatchReadiness({ ...technician, reasons: ["inactive"] })).toBe(
      "INACTIVE",
    );
  });
});
