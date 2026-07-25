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
    expect(screen.getByRole("heading", { name: "Account" }).parentElement).toHaveClass(
      "p-ui-4",
      "sm:p-ui-6",
    );
    expect(screen.getByText("Updated today").tagName).toBe("FOOTER");
  });
});
