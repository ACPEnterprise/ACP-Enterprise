import { forwardRef, type ComponentPropsWithoutRef } from "react";

import { classNames } from "../utilities/classNames";

export type VisuallyHiddenProps = ComponentPropsWithoutRef<"span">;

export const VisuallyHidden = forwardRef<HTMLSpanElement, VisuallyHiddenProps>(
  function VisuallyHidden({ className, ...props }, ref) {
    return <span ref={ref} className={classNames("sr-only", className)} {...props} />;
  },
);
