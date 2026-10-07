import { describe, expect, it } from "vitest";

import { technicianCalendarColor, UNASSIGNED_COLOR } from "./calendarIdentity";

describe("calendar identity", () => {
  it("keeps employee color stable", () => {
    expect(technicianCalendarColor("employee-1")).toEqual(
      technicianCalendarColor("employee-1"),
    );
    expect(technicianCalendarColor("employee-1")).not.toEqual(
      technicianCalendarColor("employee-2"),
    );
  });

  it("gives unassigned work a governed neutral attention treatment", () => {
    expect(technicianCalendarColor("__unassigned")).toEqual(UNASSIGNED_COLOR);
  });
});
