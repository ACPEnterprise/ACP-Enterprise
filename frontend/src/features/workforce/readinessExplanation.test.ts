import { describe, expect, it } from "vitest";

import { explainReadiness } from "./readinessExplanation";

describe("readiness explanations", () => {
  it("assigns human capability certification to the owner", () => {
    expect(explainReadiness("TECHNICIAN_CAPABILITY_NOT_READY")).toEqual({
      missing: "Technician capability has not been owner-certified.",
      actor: "OWNER",
      next: "Certify only the supported capability backed by human authority.",
    });
  });

  it("keeps password establishment with the employee", () => {
    const result = explainReadiness("PASSWORD_NOT_ESTABLISHED");
    expect(result.actor).toBe("EMPLOYEE");
    expect(result.next).toContain("administrators cannot set it");
  });

  it("fails safely for a newly introduced blocker", () => {
    const result = explainReadiness("NEW_AUTHORITY_BLOCKER");
    expect(result.actor).toBe("SYSTEM");
    expect(result.missing).toContain("new authority blocker");
    expect(result.next).toContain("review");
  });
});
