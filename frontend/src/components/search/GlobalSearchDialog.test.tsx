import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router";
import { describe, expect, it } from "vitest";

import { GlobalSearchDialog } from "./GlobalSearchDialog";
import { normalizeGlobalSearchQuery } from "./globalSearch";

function LocationOutput() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}{location.search}</output>;
}

describe("GlobalSearchDialog", () => {
  it.each([
    ["find customer Taylor history", "Taylor"],
    ["search for customer at 10 Main Street", "10 Main Street"],
    ["open CUS-000123", "CUS-000123"],
  ])("normalizes %s to %s", (input, expected) => {
    expect(normalizeGlobalSearchQuery(input)).toBe(expected);
  });

  it("routes a natural-language request into the normal customer workspace", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/jobs"]}>
        <GlobalSearchDialog onClose={() => undefined} />
        <LocationOutput />
      </MemoryRouter>,
    );

    await user.type(screen.getByRole("textbox", { name: "Search customers and history" }), "find customer Taylor history");
    await user.click(screen.getByRole("button", { name: "Search" }));

    expect(screen.getByTestId("location")).toHaveTextContent("/customers?query=Taylor");
  });
});
