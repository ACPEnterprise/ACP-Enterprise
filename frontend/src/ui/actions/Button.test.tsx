import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CirclePlus } from "lucide-react";
import { describe, expect, it, vi } from "vitest";

import { Button } from "./Button";

describe("Button", () => {
  it("uses native button semantics and prevents duplicate activation while loading", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    const { rerender } = render(<Button onClick={onClick}>Save</Button>);
    const button = screen.getByRole("button", { name: "Save" });
    expect(button).toHaveAttribute("type", "button");
    await user.click(button);
    expect(onClick).toHaveBeenCalledOnce();

    rerender(<Button loading loadingLabel="Saving" onClick={onClick}>Save</Button>);
    expect(screen.getByRole("button", { name: /save saving/i })).toBeDisabled();
    expect(screen.getByRole("button")).toHaveAttribute("aria-busy", "true");
    await user.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("hides decorative icons from assistive technology", () => {
    render(<Button leadingIcon={<CirclePlus data-testid="icon" />}>Create</Button>);
    expect(screen.getByTestId("icon").parentElement).toHaveAttribute("aria-hidden", "true");
  });
});
