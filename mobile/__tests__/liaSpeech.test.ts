import type { LiaResponse } from "../src/api/lia";
import { spokenTextForResponse } from "../src/lia/speech";

function response(answer: string, overrides: Partial<LiaResponse> = {}): LiaResponse {
  return {
    request_id: "10000000-0000-4000-8000-000000000001", conversation_id: "20000000-0000-4000-8000-000000000001",
    response_mode: "NORMAL", classification: "KNOWN", authority: "ACP_AUTHORITATIVE", answer,
    evidence: [], limitations: [], navigation: [], completeness: "COMPLETE_FOR_EMPLOYEE_SAFE_ADAPTERS", freshness: "CURRENT_QUERY",
    provider: "deterministic-acp", provider_version: "v1", policy_version: "LIA.EMPLOYEE_SAFE.v1", evidence_digest: "a".repeat(64),
    authorization_version: 1, company_id: "30000000-0000-4000-8000-000000000001", branch_ids: [], source_systems: [], missing_evidence: [],
    safe_next_action: null, as_of: "2026-09-17T12:00:00Z", generated_at: "2026-09-17T12:00:00Z", temporal: null, ...overrides,
  };
}

describe("native LIA spoken presentation", () => {
  it("does not read report structure or blocker codes aloud", () => {
    const spoken = spokenTextForResponse(response("WHAT IS TRUE: Lianne is active. WHAT IS BLOCKED: COMPENSATION_MISSING_CONFIGURATION. NEXT STEP: Review Payroll."));
    expect(spoken).toBe("Lianne is active. compensation setup is missing. Review Payroll.");
    expect(spoken).not.toMatch(/WHAT IS|MISSING_CONFIGURATION|NEXT STEP/);
  });

  it("preserves amounts, signs, percentages, references, and uncertainty", () => {
    const spoken = spokenTextForResponse(response("Job JOB-313 may show -$125.50 and -5.25% for Invoice INV-204."));
    expect(spoken).toContain("Job 313 may show negative $125.50");
    expect(spoken).toContain("negative 5.25 percent");
    expect(spoken).toContain("Invoice 204");
  });

  it("honors response depth and speaks provenance only when requested", () => {
    const evidence = [{ domain: "employee-operations", label: "My authorized assigned work", authority: "EMPLOYEE.DAY.v1", observed_at: "2026-09-17T12:00:00Z", freshness: "CURRENT_QUERY", evidence_digest: "b".repeat(64), branch_ids: [], limitations: [] }];
    expect(spokenTextForResponse(response("First. Second. Third.", { response_mode: "BRIEF", evidence }))).toBe("First. Second.");
    expect(spokenTextForResponse(response("First.", { response_mode: "EVIDENCE", evidence }))).toContain("supporting evidence comes from My authorized assigned work");
  });

  it("does not invent pronunciation for a person's name", () => {
    expect(spokenTextForResponse(response("Lianne Hernandez is ready."))).toBe("Lianne Hernandez is ready.");
  });

  it("finishes material sentences instead of truncating exact facts", () => {
    const exact = `The authorized Invoice balance is $${"1".repeat(400)}.25.`;
    expect(spokenTextForResponse(response(exact, { response_mode: "BRIEF" }))).toBe(exact);
  });

  it("handles corrections, topic switches, and missing evidence naturally", () => {
    expect(spokenTextForResponse(response("Correction: Invoice INV-204 is selected."))).toBe("Got it — Invoice 204 is selected.");
    expect(spokenTextForResponse(response("Topic changed: Your next Job is tomorrow."))).toBe("Now, your next Job is tomorrow.");
    expect(spokenTextForResponse(response("Evidence unavailable."))).toBe("I don't have that evidence yet.");
  });
});
