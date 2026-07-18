import { forwardRef, type ComponentPropsWithoutRef } from "react";

import { classNames } from "../utilities/classNames";
import { combineIds, useFieldContext } from "./FieldContext";
import { controlClasses } from "./controlStyles";

export type TextareaProps = ComponentPropsWithoutRef<"textarea">;

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { "aria-describedby": ariaDescribedBy, "aria-invalid": ariaInvalid, className, disabled, id, required, ...props },
  ref,
) {
  const field = useFieldContext();
  return (
    <textarea
      ref={ref}
      id={id ?? field?.controlId}
      disabled={disabled ?? field?.disabled}
      required={required ?? field?.required}
      aria-invalid={ariaInvalid ?? (field?.invalid || undefined)}
      aria-describedby={combineIds(ariaDescribedBy, field?.describedBy)}
      className={classNames(controlClasses, "min-h-24 resize-y", className)}
      {...props}
    />
  );
});
