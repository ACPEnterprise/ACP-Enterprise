import { describe, expect, it } from "vitest";

import { dayRange, localDateValue, moveDate, operationalJobStatuses } from "./dispatchPresentation";

describe("Dispatch presentation scope", () => {
  it("builds a half-open local-day range and handles date rollover", () => {
    const range = dayRange("2026-07-23");
    expect(new Date(range.endAt).getTime() - new Date(range.startAt).getTime()).toBe(86_400_000);
    expect(moveDate("2026-07-31", 1)).toBe("2026-08-01");
    expect(moveDate("2026-01-01", -1)).toBe("2025-12-31");
    expect(localDateValue(new Date(2026, 6, 23))).toBe("2026-07-23");
  });
  it("uses only nonterminal Job lifecycle states for operational presentation", () => {
    expect(operationalJobStatuses).toEqual(["draft", "ready", "in_progress", "paused"]);
  });
});
