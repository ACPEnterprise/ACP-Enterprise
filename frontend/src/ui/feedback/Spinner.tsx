import { forwardRef, type ComponentPropsWithoutRef } from "react";

import { classNames } from "../utilities/classNames";

export type SpinnerSize = "small" | "medium" | "large";

interface SpinnerBaseProps extends Omit<ComponentPropsWithoutRef<"span">, "children"> {
  size?: SpinnerSize;
}

export type SpinnerProps = SpinnerBaseProps &
  (
    | { decorative: true; label?: never }
    | { decorative?: false; label: string }
  );

const sizeClasses: Record<SpinnerSize, string> = {
  small: "size-[var(--icon-small)] border-2",
  medium: "size-[var(--icon-medium)] border-2",
  large: "size-[var(--icon-large)] border-[3px]",
};

export const Spinner = forwardRef<HTMLSpanElement, SpinnerProps>(function Spinner(
  { className, decorative = false, label, size = "medium", ...props },
  ref,
) {
  return (
    <span
      ref={ref}
      className={classNames(
        "inline-block shrink-0 animate-spin rounded-full border-current border-r-transparent motion-reduce:animate-none",
        sizeClasses[size],
        className,
      )}
      role={decorative ? undefined : "status"}
      aria-label={decorative ? undefined : label}
      aria-hidden={decorative ? true : undefined}
      {...props}
    />
  );
});
