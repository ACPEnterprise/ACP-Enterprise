import { describe, expect, it } from "vitest";
import { quarterHourDropMinute } from "./calendarDragDrop";

describe("quarterHourDropMinute", () => {
  it("snaps visual drops to the office quarter-hour grid", () => {
    expect(quarterHourDropMinute(7 * 60, 12 * 60, 52)).toBe(7 * 60 + 45);
    expect(quarterHourDropMinute(7 * 60, 12 * 60, 59)).toBe(8 * 60);
  });

  it("does not derive a time outside Branch display bounds", () => {
    expect(quarterHourDropMinute(7 * 60, 12 * 60, -50)).toBe(7 * 60);
    expect(quarterHourDropMinute(7 * 60, 12 * 60, 900)).toBe(19 * 60);
  });
});
