import { forwardRef, type ComponentPropsWithoutRef } from "react";

import { classNames } from "../utilities/classNames";
import { combineIds, useFieldContext } from "./FieldContext";
import { controlClasses } from "./controlStyles";

export type InputProps = ComponentPropsWithoutRef<"input">;

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { "aria-describedby": ariaDescribedBy, "aria-invalid": ariaInvalid, className, disabled, id, required, ...props },
  ref,
) {
  const field = useFieldContext();
  return (
    <input
      ref={ref}
      id={id ?? field?.controlId}
      disabled={disabled ?? field?.disabled}
      required={required ?? field?.required}
      aria-invalid={ariaInvalid ?? (field?.invalid || undefined)}
      aria-describedby={combineIds(ariaDescribedBy, field?.describedBy)}
      className={classNames(controlClasses, className)}
      {...props}
    />
  );
});
