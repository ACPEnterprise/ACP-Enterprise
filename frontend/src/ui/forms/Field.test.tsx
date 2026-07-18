import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Field } from "./Field";
import { Input } from "./Input";

describe("Field", () => {
  it("associates its label, descriptions, required state, and validation", () => {
    render(
      <Field label="Email" helperText="Work address" validationMessage="Email is invalid" required>
        <Input type="email" />
      </Field>,
    );
    const input = screen.getByRole("textbox", { name: /email required/i });
    expect(input).toBeRequired();
    expect(input).toHaveAccessibleDescription("Work address Email is invalid");
    expect(input).toHaveAttribute("aria-invalid", "true");
  });

  it("propagates disabled state", () => {
    render(<Field label="Code" disabled><Input /></Field>);
    expect(screen.getByRole("textbox", { name: "Code" })).toBeDisabled();
  });
});
