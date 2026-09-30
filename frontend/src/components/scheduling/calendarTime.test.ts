import { describe, expect, it } from "vitest";

import {
  branchInputInstant,
  branchLocalInput,
  calendarDateKey,
  calendarMinute,
} from "./calendarTime";

describe("Branch-local calendar time", () => {
  it("keeps a New York appointment on its authoritative local day", () => {
    const instant = "2026-11-02T14:30:00.000Z";
    expect(calendarDateKey(instant, "America/New_York")).toBe("2026-11-02");
    expect(calendarMinute(instant, "America/New_York")).toBe(570);
    expect(branchLocalInput(instant, "America/New_York")).toBe(
      "2026-11-02T09:30",
    );
    expect(
      branchInputInstant("2026-11-02T09:30", "America/New_York").toISOString(),
    ).toBe(instant);
  });

  it("rejects a nonexistent DST wall time", () => {
    expect(() =>
      branchInputInstant("2026-03-08T02:30", "America/New_York"),
    ).toThrow(/does not exist/);
  });
});
