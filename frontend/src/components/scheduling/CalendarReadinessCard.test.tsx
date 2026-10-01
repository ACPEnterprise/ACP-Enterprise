import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { CalendarReadinessCard } from "./CalendarReadinessCard";

describe("CalendarReadinessCard", () => {
  it("keeps partial completeness compact until the operator opens details", async () => {
    render(
      <CalendarReadinessCard
        appointments={[]}
        appointmentTotal={14}
        jobs={[]}
        jobTotal={15}
        unavailable
      />,
    );
    expect(screen.getAllByText("PARTIAL")[0]).toBeVisible();
    expect(screen.getByText("Calendar Attention 4")).toBeVisible();
    expect(screen.getByText(/No missing count is inferred/)).not.toBeVisible();
    await userEvent.click(screen.getByText("Calendar Attention 4"));
    expect(screen.getByText(/No missing count is inferred/)).toBeVisible();
  });
});
