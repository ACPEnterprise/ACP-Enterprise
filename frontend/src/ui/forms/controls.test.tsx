import { createRef } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Checkbox } from "./Checkbox";
import { Field } from "./Field";
import { Input } from "./Input";
import { Select } from "./Select";
import { Textarea } from "./Textarea";

describe("form controls", () => {
  it("forwards native refs and attributes", () => {
    const inputRef = createRef<HTMLInputElement>();
    render(<Input ref={inputRef} readOnly value="ACP" aria-label="Product" />);
    expect(inputRef.current).toBe(screen.getByRole("textbox", { name: "Product" }));
    expect(inputRef.current).toHaveAttribute("readonly");
  });

  it("keeps select and textarea native", () => {
    render(<><Select aria-label="Status"><option>Active</option></Select><Textarea aria-label="Notes" /></>);
    expect(screen.getByRole("combobox", { name: "Status" })).toBeInstanceOf(HTMLSelectElement);
    expect(screen.getByRole("textbox", { name: "Notes" })).toBeInstanceOf(HTMLTextAreaElement);
  });

  it("supports native checkbox interaction, field descriptions, and indeterminate state", async () => {
    const user = userEvent.setup();
    const ref = createRef<HTMLInputElement>();
    render(
      <Field helperText="Includes archived records">
        <Checkbox ref={ref} label="Show all" indeterminate />
      </Field>,
    );
    const checkbox = screen.getByRole("checkbox", { name: "Show all" });
    expect(ref.current?.indeterminate).toBe(true);
    expect(checkbox).toHaveAttribute("aria-checked", "mixed");
    expect(checkbox).toHaveAccessibleDescription("Includes archived records");
    await user.click(checkbox);
    expect(checkbox).toBeChecked();
  });
});
