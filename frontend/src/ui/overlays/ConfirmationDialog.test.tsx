import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { ConfirmationDialog } from "./ConfirmationDialog";

function DialogHarness({
  onConfirm = () => undefined,
}: {
  readonly onConfirm?: () => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Open confirmation
      </button>
      {open && (
        <ConfirmationDialog
          title="Approve change?"
          description="Review this action before continuing."
          confirmLabel="Approve"
          onCancel={() => setOpen(false)}
          onConfirm={onConfirm}
        >
          <p>Execution remains disconnected.</p>
        </ConfirmationDialog>
      )}
    </>
  );
}

describe("ConfirmationDialog", () => {
  it("uses modal semantics, locks background scrolling, and starts on the safe action", async () => {
    const user = userEvent.setup();
    const root = document.createElement("div");
    root.id = "root";
    document.body.append(root);
    render(<DialogHarness />, { container: root });

    await user.click(screen.getByRole("button", { name: "Open confirmation" }));

    expect(screen.getByRole("dialog", { name: "Approve change?" })).toHaveAttribute(
      "aria-modal",
      "true",
    );
    expect(screen.getByText("Review this action before continuing.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Go back" })).toHaveFocus();
    expect(document.body.style.overflow).toBe("hidden");
    expect(root).toHaveAttribute("inert");

    await user.click(screen.getByRole("button", { name: "Go back" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open confirmation" })).toHaveFocus();
    expect(document.body.style.overflow).toBe("");
    expect(root).not.toHaveAttribute("inert");
    root.remove();
  });

  it("traps focus and closes with Escape without confirming", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(<DialogHarness onConfirm={onConfirm} />);

    await user.click(screen.getByRole("button", { name: "Open confirmation" }));
    const cancel = screen.getByRole("button", { name: "Go back" });
    const confirm = screen.getByRole("button", { name: "Approve" });

    cancel.focus();
    await user.keyboard("{Shift>}{Tab}{/Shift}");
    expect(confirm).toHaveFocus();
    await user.keyboard("{Tab}");
    expect(cancel).toHaveFocus();
    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("blocks dismissal and duplicate confirmation while pending", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    const onConfirm = vi.fn();
    render(
      <ConfirmationDialog
        title="Cancel command?"
        confirmLabel="Cancel command"
        destructive
        pending
        onCancel={onCancel}
        onConfirm={onConfirm}
      />,
    );

    expect(screen.getByRole("button", { name: "Go back" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /cancel command/i })).toBeDisabled();
    await user.keyboard("{Escape}");
    expect(onCancel).not.toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
