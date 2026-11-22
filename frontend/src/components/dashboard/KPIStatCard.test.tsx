import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { KPIStatCard } from "./KPIStatCard";

describe("KPIStatCard", () => {
  it("uses the shared dashboard card border treatment", () => {
    render(<MemoryRouter><KPIStatCard label="Revenue" value="$1,200" href="/mission-control/drilldown?metric=booked_revenue" /></MemoryRouter>);

    expect(screen.getByRole("article")).toHaveClass("dashboard-card-border");
    expect(screen.getByRole("link", { name: "Revenue: $1,200" })).toHaveAttribute("href", "/mission-control/drilldown?metric=booked_revenue");
  });
});
