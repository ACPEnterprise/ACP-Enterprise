import { useId, type ComponentPropsWithoutRef, type ReactNode } from "react";

import { VisuallyHidden } from "../accessibility/VisuallyHidden";
import { classNames } from "../utilities/classNames";
import { FieldContext } from "./FieldContext";

export interface FieldProps extends ComponentPropsWithoutRef<"div"> {
  label?: ReactNode;
  helperText?: ReactNode;
  validationMessage?: ReactNode;
  required?: boolean;
  disabled?: boolean;
  controlId?: string;
}

export function Field({
  children,
  className,
  controlId: suppliedControlId,
  disabled = false,
  helperText,
  label,
  required = false,
  validationMessage,
  ...props
}: FieldProps) {
  const generatedId = useId();
  const controlId = suppliedControlId ?? `field-${generatedId}`;
  const descriptionId = helperText ? `${controlId}-description` : undefined;
  const errorId = validationMessage ? `${controlId}-error` : undefined;
  const describedBy = [descriptionId, errorId].filter(Boolean).join(" ") || undefined;

  return (
    <FieldContext.Provider
      value={{ controlId, describedBy, invalid: Boolean(validationMessage), required, disabled }}
    >
      <div
        className={classNames(
          "flex flex-col gap-ui-2 text-body-s",
          disabled && "text-[var(--semantic-disabled-content)]",
          className,
        )}
        {...props}
      >
        {label && (
          <label htmlFor={controlId} className="font-medium text-content-secondary">
            {label}
            {required && (
              <>
                <span aria-hidden="true" className="ml-ui-1 text-status-danger">*</span>
                {" "}
                <VisuallyHidden>required</VisuallyHidden>
              </>
            )}
          </label>
        )}
        {children}
        {helperText && <p id={descriptionId} className="text-caption text-content-muted">{helperText}</p>}
        {validationMessage && (
          <p id={errorId} className="text-caption font-medium text-status-danger">{validationMessage}</p>
        )}
      </div>
    </FieldContext.Provider>
  );
}
