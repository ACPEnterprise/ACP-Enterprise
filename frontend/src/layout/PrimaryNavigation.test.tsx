import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { availableNavigation } from "./navigation";
import { PrimaryNavigation } from "./PrimaryNavigation";

describe("PrimaryNavigation", () => {
  it("renders only operational links and derives active state from the route", () => {
    render(<MemoryRouter initialEntries={["/customers"]}><PrimaryNavigation items={availableNavigation} /></MemoryRouter>);
    expect(screen.getByRole("link", { name: "Customers" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Mission Control" })).not.toHaveAttribute("aria-current");
    expect(screen.queryByText("Dispatch")).not.toBeInTheDocument();
  });

  it("retains accessible names when collapsed", () => {
    render(<MemoryRouter><PrimaryNavigation items={availableNavigation} collapsed /></MemoryRouter>);
    expect(screen.getByRole("link", { name: "Mission Control" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Customers" })).toBeInTheDocument();
  });
});
