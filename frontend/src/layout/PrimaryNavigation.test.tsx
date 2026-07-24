import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { navigationGroups } from "./navigation";
import { PrimaryNavigation } from "./PrimaryNavigation";

describe("PrimaryNavigation", () => {
  it("renders only operational links and derives active state from the route", () => {
    render(<MemoryRouter initialEntries={["/customers"]}><PrimaryNavigation groups={navigationGroups} /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Operations" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Customers" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Mission Control" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("link", { name: "Dispatch" })).toHaveAttribute("href", "/dispatch");
    expect(screen.getByRole("link", { name: "Engineering Factory" })).toHaveAttribute("href", "/engineering");
    expect(screen.getByLabelText("Scheduling, Coming Soon")).toHaveAttribute("aria-disabled", "true");
    expect(screen.queryByRole("link", { name: "Scheduling" })).not.toBeInTheDocument();
  });

  it("retains accessible names when collapsed", () => {
    render(<MemoryRouter><PrimaryNavigation groups={navigationGroups} collapsed /></MemoryRouter>);
    expect(screen.getByRole("link", { name: "Command Center" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Mission Control" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Customers" })).toBeInTheDocument();
    expect(screen.getByLabelText("Settings, Coming Soon")).toBeInTheDocument();
  });
});
