import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Bell } from "lucide-react";
import { describe, expect, it, vi } from "vitest";

import { IconButton } from "./IconButton";

describe("IconButton", () => {
  it("has a required accessible label and native keyboard behavior", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<IconButton icon={<Bell />} label="Notifications" onClick={onClick} />);
    const button = screen.getByRole("button", { name: "Notifications" });
    button.focus();
    await user.keyboard("{Enter}");
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("preserves its accessible name while loading", () => {
    render(<IconButton loading icon={<Bell />} label="Notifications" />);
    expect(screen.getByRole("button", { name: "Notifications" })).toBeDisabled();
  });
});
