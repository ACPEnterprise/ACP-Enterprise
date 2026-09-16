import { describe, expect, it } from "vitest";

import { VOICE_ACCEPTANCE_CORPUS } from "./voiceAcceptanceCorpus";
import { classifyVoiceIntent, matchingAuthorizedNavigation } from "./voiceIntent";

describe("LIA voice intent safety", () => {
  it("qualifies more than one hundred deterministic transcripts", () => {
    expect(VOICE_ACCEPTANCE_CORPUS).toHaveLength(120);
    expect(new Set(VOICE_ACCEPTANCE_CORPUS.map((item) => item.id)).size).toBe(120);
    for (const testCase of VOICE_ACCEPTANCE_CORPUS) {
      expect(classifyVoiceIntent(testCase.transcript).kind, testCase.id).toBe(
        testCase.expectedIntent,
      );
    }
  });

  it("navigates only through a matching server-authorized destination", () => {
    const navigation = [
      { label: "Open Payroll", internal_path: "/payroll" },
      { label: "Open Workforce", internal_path: "/employees" },
    ];
    expect(matchingAuthorizedNavigation("Open Payroll", navigation)).toEqual(
      navigation[0],
    );
    expect(matchingAuthorizedNavigation("Open Dispatch", navigation)).toBeUndefined();
    expect(
      matchingAuthorizedNavigation("Move this appointment", navigation),
    ).toBeUndefined();
  });

  it("classifies high-impact requests but exposes no execution contract", () => {
    expect(classifyVoiceIntent("Raise this price five percent")).toEqual({
      kind: "MUTATION_REQUEST",
      action: "PRICE_BOOK_CHANGE",
    });
    expect(classifyVoiceIntent("Post this journal")).toEqual({
      kind: "MUTATION_REQUEST",
      action: "ACCOUNTING_POST",
    });
  });
});
