import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { VisuallyHidden } from "./VisuallyHidden";

describe("VisuallyHidden", () => {
  it("keeps its content in the accessibility tree", () => {
    render(<p>System status <VisuallyHidden>is operational</VisuallyHidden></p>);
    expect(screen.getByText("is operational")).toHaveClass("sr-only");
    expect(screen.getByText(/system status/i)).toHaveTextContent("System status is operational");
  });
});
