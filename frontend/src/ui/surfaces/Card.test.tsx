import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Card, CardActions, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "./Card";

describe("Card", () => {
  it("provides optional semantic composition", () => {
    render(
      <Card>
        <CardHeader><CardTitle>Account</CardTitle><CardDescription>Current account</CardDescription></CardHeader>
        <CardContent>Details</CardContent>
        <CardActions>Actions</CardActions>
        <CardFooter>Updated today</CardFooter>
      </Card>,
    );
    expect(screen.getByRole("article")).toContainElement(screen.getByRole("heading", { name: "Account" }));
    expect(screen.getByRole("article")).toHaveClass("min-w-0");
    expect(screen.getByRole("article")).toHaveClass(
      "twelve-hats-panel-outline",
      "border-2",
      "border-solid",
      "border-[var(--semantic-panel-outline)]",
      "rounded-xl",
    );
    expect(screen.getByRole("article")).toHaveAttribute("data-panel-tone", "normal");
    expect(screen.getByRole("heading", { name: "Account" }).parentElement).toHaveClass(
      "p-ui-4",
      "sm:p-ui-6",
    );
    expect(screen.getByText("Updated today").tagName).toBe("FOOTER");
  });

  it("keeps every tone on the same approved work-card border contract", () => {
    const { rerender } = render(<Card tone="warning">Review required</Card>);
    expect(screen.getByRole("article")).toHaveAttribute("data-panel-tone", "warning");
    expect(screen.getByRole("article")).toHaveClass("border-2", "border-solid", "border-[var(--semantic-panel-outline)]");
    rerender(<Card tone="danger">Critical failure</Card>);
    expect(screen.getByRole("article")).toHaveAttribute("data-panel-tone", "danger");
    expect(screen.getByRole("article")).toHaveClass("border-2", "border-solid", "border-[var(--semantic-panel-outline)]");
  });
});
