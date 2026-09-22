import { describe, expect, it } from "vitest";

import type { LiaResponse } from "../../types/lia";
import { spokenAnswer, type SpokenResponseMode } from "./voiceSpeech";

const response = (
  answer: string,
  overrides: Partial<LiaResponse> = {},
): LiaResponse => ({
  request_id: "request-1",
  conversation_id: "conversation-1",
  classification: "KNOWN",
  authority: "ACP_AUTHORITATIVE",
  answer,
  response_mode: "NORMAL",
  evidence: [],
  limitations: [],
  navigation: [],
  proposals: [],
  completeness: "COMPLETE_FOR_AUTHORIZED_ADAPTERS",
  freshness: "CURRENT_QUERY",
  provider: "deterministic-acp",
  provider_version: "v1",
  policy_version: "v1",
  evidence_digest: "a".repeat(64),
  authorization_version: 1,
  company_id: "11111111-1111-4111-8111-111111111111",
  branch_ids: [],
  subject_domain: null,
  subject_id: null,
  source_systems: [],
  missing_evidence: [],
  safe_next_action: null,
  as_of: "2026-09-17T12:00:00Z",
  generated_at: "2026-09-17T12:00:00Z",
  ...overrides,
});

describe("LIA spoken presentation", () => {
  it.each<{
    family: string;
    answer: string;
    expected: string[];
    absent?: string[];
    overrides?: Partial<LiaResponse>;
  }>([
    {
      family: "Customer",
      answer: "Customer status active. Jobs count 7. Balance 842 dollars.",
      expected: ["I found the customer", "they're active", "7 jobs", "$842"],
      absent: ["Customer status", "Jobs count"],
    },
    {
      family: "Job",
      answer: "Job JOB-313 is complete. Jason is assigned. The appointment is tomorrow at 9:00 AM.",
      expected: ["Job 313", "Jason", "tomorrow", "9:00 AM"],
    },
    {
      family: "Scheduling",
      answer: "Two appointments are scheduled tomorrow. One is still unassigned.",
      expected: ["Two appointments", "tomorrow", "unassigned"],
      overrides: { safe_next_action: "Open Scheduling" },
    },
    {
      family: "Employee",
      answer: "Lianne Hernandez is active. She is mobile-ready. Her Membership is active.",
      expected: ["Lianne Hernandez", "mobile-ready", "Membership"],
    },
    {
      family: "Invoice",
      answer: "Invoice INV-204 is open. The authoritative balance is $842.15 as of September 17, 2026.",
      expected: ["Invoice 204", "$842.15", "September 17, 2026"],
    },
    {
      family: "Payroll blocker",
      answer: "Lianne is not payroll-ready. COMPENSATION_MISSING_CONFIGURATION. TIME_EVIDENCE_MISSING.",
      expected: ["Lianne isn't payroll-ready", "compensation setup is missing", "accepted time is missing"],
      absent: ["COMPENSATION_MISSING_CONFIGURATION", "TIME_EVIDENCE_MISSING"],
    },
    {
      family: "Financial comparison",
      answer: "QuickBooks source evidence shows May income of $125,000 and June income of $130,000. The reports use the accrual basis.",
      expected: ["$125,000", "$130,000", "accrual basis", "source evidence"],
      overrides: { authority: "SOURCE_BACKED" },
    },
    {
      family: "Price Book",
      answer: "Drain cleaning is currently $289.00 in the Main Branch. Cost and margin are not included.",
      expected: ["Drain cleaning", "$289.00", "Main Branch", "Cost and margin aren't included"],
    },
    {
      family: "Ambiguity",
      answer: "I found two customers named John Smith. Which one do you mean: Clearwater or Main Street?",
      expected: ["two customers", "Clearwater", "Main Street"],
    },
    {
      family: "Missing evidence",
      answer: "I found the Job, but accepted material cost is not available yet. I cannot calculate contribution without it.",
      expected: ["accepted material cost isn't available", "I can't calculate contribution"],
    },
  ])("keeps $family facts while making delivery natural", ({ answer, expected, absent, overrides }) => {
    const spoken = spokenAnswer(response(answer, overrides));
    for (const fragment of expected) expect(spoken).toContain(fragment);
    for (const fragment of absent ?? []) expect(spoken).not.toContain(fragment);
    expect(spoken).not.toContain("Next:");
    expect(spoken).not.toMatch(/[A-Z]{3,}_[A-Z_]+/);
  });

  it.each<[SpokenResponseMode, string, string | null]>([
    ["BRIEF", "First. Second.", "Third."],
    ["NORMAL", "First. Second. Third.", "Fourth."],
    ["DETAILED", "First. Second. Third. Fourth. Fifth. Sixth.", "Seventh."],
    ["EVIDENCE", "First. Second. Third. Fourth. Fifth. Sixth. Seventh. Eighth.", null],
  ])("honors %s sentence depth", (mode, included, excluded) => {
    const spoken = spokenAnswer(
      response("First. Second. Third. Fourth. Fifth. Sixth. Seventh. Eighth. Ninth."),
      mode,
    );
    expect(spoken).toContain(included);
    if (excluded) expect(spoken).not.toContain(excluded);
  });

  it("does not speak long opaque identifiers", () => {
    const spoken = spokenAnswer(
      response(
        "Customer 45f0cd83-4ea6-4aa0-8cb1-b40780bf2409 is active. Their name is Acme Plumbing.",
      ),
    );
    expect(spoken).not.toContain("45f0cd83");
    expect(spoken).toContain("Acme Plumbing");
  });

  it("preserves material spoken semantics while normalizing pronunciation", () => {
    const spoken = spokenAnswer(
      response(
        "ACP's P&L shows -$125.50, down -5.25%, across 7 jobs on September 17, 2026 at 9:30 AM. JOB-313, INV-204, EST-19, and APT-267 remain available.",
      ),
      "EVIDENCE",
    );

    expect(spoken).toContain("profit and loss");
    expect(spoken).toContain("negative $125.50");
    expect(spoken).toContain("negative 5.25 percent");
    expect(spoken).toContain("7 jobs");
    expect(spoken).toContain("September 17, 2026");
    expect(spoken).toContain("9:30 AM");
    expect(spoken).toContain("Job 313");
    expect(spoken).toContain("Invoice 204");
    expect(spoken).toContain("Estimate 19");
    expect(spoken).toContain("Appointment 267");
    expect(spoken).toContain("remain available");
  });

  it("preserves uncertainty and source authority without changing a person's name", () => {
    const spoken = spokenAnswer(
      response("Lianne Hernandez may be missing accepted time; the evidence is incomplete.", {
        authority: "SOURCE_BACKED",
      }),
    );

    expect(spoken).toContain("Lianne Hernandez");
    expect(spoken).toContain("may be missing");
    expect(spoken).toContain("incomplete");
    expect(spoken).toContain("source-backed evidence");
  });

  it("turns structured report headings into connected spoken sentences", () => {
    const spoken = spokenAnswer(
      response("WHAT IS TRUE: Lianne is active. WHAT IS BLOCKED: Accepted time is missing. NEXT STEP: Review this pay period."),
    );
    expect(spoken).toBe(
      "Lianne is active. Accepted time is missing. Review this pay period.",
    );
    expect(spoken).not.toMatch(/WHAT IS|NEXT STEP/);
  });

  it("speaks bounded provenance only in evidence mode", () => {
    const withEvidence = response("The Invoice is open.", {
      evidence: [
        {
          domain: "invoicing",
          label: "Authorized Invoice state",
          authority: "INVOICE.v1",
          observed_at: "2026-09-17T12:00:00Z",
          freshness: "CURRENT_QUERY",
          evidence_digest: "b".repeat(64),
          entity_id: null,
          count: 1,
          state: "open",
        },
      ],
    });
    expect(spokenAnswer(withEvidence, "NORMAL")).not.toContain("supporting evidence");
    const spoken = spokenAnswer(withEvidence, "EVIDENCE");
    expect(spoken).toContain("supporting evidence comes from Authorized Invoice state");
    expect(spoken).toContain("September 17, 2026");
    expect(spoken).toContain("12:00 PM UTC");
  });

  it("finishes material sentences instead of truncating exact facts", () => {
    const exact = `The authorized Invoice balance is $${"1".repeat(400)}.25.`;
    expect(spokenAnswer(response(exact), "BRIEF")).toBe(exact);
  });

  it("acknowledges corrections and topic changes without changing the fact", () => {
    expect(spokenAnswer(response("Correction: Invoice INV-204 is the selected record."))).toBe(
      "Got it — Invoice 204 is the selected record.",
    );
    expect(spokenAnswer(response("Topic changed: Two appointments are scheduled tomorrow."))).toBe(
      "Now, two appointments are scheduled tomorrow.",
    );
  });

  it("states unavailable evidence in plain language", () => {
    expect(spokenAnswer(response("No authorized authoritative evidence is available for this question."))).toBe(
      "I don't have authorized evidence for that yet.",
    );
  });
});
