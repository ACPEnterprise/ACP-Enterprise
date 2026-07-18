import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Badge } from "./Badge";

describe("Badge", () => {
  it("is presentational by default and supports explicit status semantics", () => {
    const { rerender } = render(<Badge variant="success">Operational</Badge>);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByText("Operational")).toBeVisible();
    rerender(<Badge role="status">Updated</Badge>);
    expect(screen.getByRole("status")).toHaveTextContent("Updated");
  });
});
