import { describe, expect, it } from "vitest";

import {
  DELIVERY_NATURALNESS_CORPUS,
  evaluateDeliveryCase,
} from "./voiceDeliveryNaturalness";

describe("LIA delivery A/B corpus", () => {
  it("covers the required owner-facing delivery families", () => {
    expect(new Set(DELIVERY_NATURALNESS_CORPUS.map((item) => item.family))).toEqual(
      new Set([
        "factual_answer",
        "owner_brief",
        "clarification",
        "missing_evidence",
        "payroll_blocker",
        "dispatch_warning",
        "positive_result",
        "step_by_step",
        "economic_answer",
        "employee_context",
      ]),
    );
  });

  it.each(DELIVERY_NATURALNESS_CORPUS)(
    "$id preserves A/B semantics and realizes $expectedIntent delivery",
    (item) => {
      const result = evaluateDeliveryCase(item);
      expect(result.baseline.text).toBe(item.text);
      expect(result.successor.semanticText).toBe(item.text);
      expect(result.successor.intent).toBe(item.expectedIntent);
      expect(result.semanticEquivalent).toBe(true);
      expect(result.materialValuesPreserved).toBe(true);
      expect(result.successor.groups.every((group) => group.text.length > 0)).toBe(true);
    },
  );
});
