import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CalendarReadinessCard } from "./CalendarReadinessCard";

describe("CalendarReadinessCard", () => {
  it("does not invent completeness from a partial native query", () => {
    render(
      <CalendarReadinessCard
        appointments={[]}
        appointmentTotal={14}
        jobs={[]}
        jobTotal={15}
        unavailable
      />,
    );
    expect(screen.getByText("PARTIAL")).toBeVisible();
    expect(screen.getByText(/No missing count is inferred/)).toBeVisible();
  });
});
