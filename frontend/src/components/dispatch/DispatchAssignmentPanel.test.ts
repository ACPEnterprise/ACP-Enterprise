import { describe, expect, it } from "vitest";

import type { TechnicianEligibility } from "../../types/dispatch";
import { canPrepareFieldReadiness } from "./fieldReadiness";

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

describe("Dispatch field-readiness selection", () => {
  it("allows an authorized operator to select a profile-less employee for explicit preparation", () => {
    expect(
      canPrepareFieldReadiness(profileless, [
        "COMPANY_WORKFORCE_CAPABILITY_MANAGE",
        "COMPANY_WORKFORCE_AVAILABILITY_MANAGE",
      ]),
    ).toBe(true);
  });

  it("keeps non-preparable and unauthorized employees unavailable", () => {
    expect(canPrepareFieldReadiness(profileless, [])).toBe(false);
    expect(
      canPrepareFieldReadiness(
        { ...profileless, reasons: ["branch_scope_mismatch"] },
        [
          "COMPANY_WORKFORCE_CAPABILITY_MANAGE",
          "COMPANY_WORKFORCE_AVAILABILITY_MANAGE",
        ],
      ),
    ).toBe(false);
  });
});
