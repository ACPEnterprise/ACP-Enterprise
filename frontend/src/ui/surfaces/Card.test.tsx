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
    expect(screen.getByText("Updated today").tagName).toBe("FOOTER");
  });
});
