import { describe, expect, it } from "vitest";

import type { TechnicianEligibility } from "../../types/dispatch";
import { isFieldAssignmentCandidate } from "./fieldReadiness";

const profileless: TechnicianEligibility = {
  employee_id: "employee-lianne",
  employee_number: "EMP-TEST",
  display_name: "Lianne Hernandez",
  branch_id: "branch-main",
  job_title: "Office Manager",
  capability_codes: [],
  language_codes: [],
  eligible: false,
  decision: "not_eligible",
  reasons: [
    "missing_workforce_profile",
    "missing_required_capability",
    "availability_unknown",
  ],
  availability_confidence: "unknown",
};

describe("Dispatch field-assignment selection", () => {
  it("does not treat a profile-less Office Manager as a field candidate", () => {
    expect(isFieldAssignmentCandidate(profileless)).toBe(false);
  });

  it("requires explicit technician capability for a selector candidate", () => {
    expect(
      isFieldAssignmentCandidate({
        ...profileless,
        capability_codes: ["technician"],
      }),
    ).toBe(true);
  });
});
