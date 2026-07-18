import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Spinner } from "./Spinner";

describe("Spinner", () => {
  it("labels an active loading state", () => {
    render(<Spinner label="Loading records" />);
    expect(screen.getByRole("status", { name: "Loading records" })).toBeVisible();
  });

  it("can be explicitly decorative", () => {
    const { container } = render(<Spinner decorative />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(container.firstChild).toHaveAttribute("aria-hidden", "true");
  });
});
