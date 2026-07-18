import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Button } from "../actions/Button";
import { EmptyState } from "./EmptyState";

describe("EmptyState", () => {
  it("labels its section and composes actions", () => {
    render(
      <EmptyState
        title="No records"
        description="Create a record to begin."
        primaryAction={<Button>Create</Button>}
      />,
    );
    expect(screen.getByRole("region", { name: "No records" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Create" })).toBeEnabled();
  });
});
