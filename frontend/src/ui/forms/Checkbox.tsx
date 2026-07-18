import {
  forwardRef,
  useCallback,
  useEffect,
  useRef,
  type ComponentPropsWithoutRef,
  type ReactNode,
} from "react";

import { VisuallyHidden } from "../accessibility/VisuallyHidden";
import { classNames } from "../utilities/classNames";
import { combineIds, useFieldContext } from "./FieldContext";

export interface CheckboxProps
  extends Omit<ComponentPropsWithoutRef<"input">, "type" | "children"> {
  label: ReactNode;
  indeterminate?: boolean;
}

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(
  function Checkbox(
    {
      "aria-describedby": ariaDescribedBy,
      className,
      disabled,
      id,
      indeterminate = false,
      label,
      required,
      ...props
    },
    forwardedRef,
  ) {
    const field = useFieldContext();
    const inputRef = useRef<HTMLInputElement | null>(null);
    const setRef = useCallback(
      (node: HTMLInputElement | null) => {
        inputRef.current = node;
        if (typeof forwardedRef === "function") forwardedRef(node);
        else if (forwardedRef) forwardedRef.current = node;
      },
      [forwardedRef],
    );

    useEffect(() => {
      if (inputRef.current) inputRef.current.indeterminate = indeterminate;
    }, [indeterminate]);

    const controlId = id ?? field?.controlId;
    const isRequired = required ?? field?.required;
    return (
      <label htmlFor={controlId} className="inline-flex w-fit items-start gap-ui-3 text-body-s text-content-secondary">
        <input
          ref={setRef}
          id={controlId}
          type="checkbox"
          disabled={disabled ?? field?.disabled}
          required={isRequired}
          aria-checked={indeterminate ? "mixed" : undefined}
          aria-invalid={field?.invalid || undefined}
          aria-describedby={combineIds(ariaDescribedBy, field?.describedBy)}
          className={classNames(
            "mt-ui-1 size-[var(--icon-small)] shrink-0 rounded-sm border border-stroke-strong accent-action-primary disabled:cursor-not-allowed disabled:opacity-60",
            className,
          )}
          {...props}
        />
        <span>
          {label}
          {isRequired && (
            <>
              {" "}
              <VisuallyHidden>required</VisuallyHidden>
            </>
          )}
        </span>
      </label>
    );
  },
);
