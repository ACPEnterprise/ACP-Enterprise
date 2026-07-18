import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Cluster } from "./Cluster";
import { Inline } from "./Inline";
import { Stack } from "./Stack";

describe("layout primitives", () => {
  it("maps spacing to centralized token utilities", () => {
    render(<Stack data-testid="stack" space="large"><span>One</span><span>Two</span></Stack>);
    expect(screen.getByTestId("stack")).toHaveClass("flex-col", "gap-ui-6");
  });

  it("keeps Inline unwrapped and Cluster wrapped", () => {
    render(<><Inline data-testid="inline" /><Cluster data-testid="cluster" justify="between" /></>);
    expect(screen.getByTestId("inline")).toHaveClass("flex-nowrap");
    expect(screen.getByTestId("cluster")).toHaveClass("flex-wrap", "justify-between");
  });
});
