import { describe, expect, it } from "vitest";

import { VOICE_ACCEPTANCE_CORPUS } from "./voiceAcceptanceCorpus";
import {
  classifyVoiceIntent,
  isSafeInternalNavigationPath,
  matchingAuthorizedNavigation,
} from "./voiceIntent";

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
    expect(classifyVoiceIntent("What did they pay us last time?")).toEqual({
      kind: "QUESTION",
    });
    expect(classifyVoiceIntent("How much did we collect last month?")).toEqual({
      kind: "QUESTION",
    });
  });
});

describe("safe navigation", () => {
  it.each([
    "https://outside.invalid/payroll",
    "//outside.invalid/payroll",
    "/jobs/../payroll",
    "/jobs\\outside",
  ])("rejects unbounded destination %s", (path) => {
    expect(isSafeInternalNavigationPath(path)).toBe(false);
    expect(
      matchingAuthorizedNavigation("Open payroll", [
        { label: "Open Payroll", internal_path: path },
      ]),
    ).toBeUndefined();
  });

  it("accepts a bounded internal destination", () => {
    expect(isSafeInternalNavigationPath("/payroll?period=current#review")).toBe(true);
  });
});
