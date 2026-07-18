import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Alert } from "./Alert";

describe("Alert", () => {
  it("does not announce static content automatically", () => {
    render(<Alert title="Review">Check the submitted values.</Alert>);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByText("Check the submitted values.")).toBeVisible();
  });

  it("supports explicit polite and assertive announcements", () => {
    const { rerender } = render(<Alert announcement="polite">Saved</Alert>);
    expect(screen.getByRole("status")).toHaveAttribute("aria-live", "polite");
    rerender(<Alert announcement="assertive">Connection lost</Alert>);
    expect(screen.getByRole("alert")).toHaveAttribute("aria-live", "assertive");
  });
});
