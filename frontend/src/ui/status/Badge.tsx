import {
  forwardRef,
  type ComponentPropsWithoutRef,
  type ReactNode,
} from "react";

import { classNames } from "../utilities/classNames";

export type BadgeVariant =
  | "neutral"
  | "information"
  | "success"
  | "warning"
  | "danger";
export interface BadgeProps
  extends Omit<ComponentPropsWithoutRef<"span">, "role"> {
  variant?: BadgeVariant;
  role?: "status";
  icon?: ReactNode;
}

const variantClasses: Record<BadgeVariant, string> = {
  neutral: "bg-surface-muted text-content-secondary",
  information: "bg-status-information/15 text-status-information",
  success: "bg-status-success/15 text-status-success",
  warning: "bg-status-warning/15 text-status-warning",
  danger: "bg-status-danger/15 text-status-danger",
};

export const Badge = forwardRef<HTMLSpanElement, BadgeProps>(function Badge(
  { children, className, icon, role, variant = "neutral", ...props },
  ref,
) {
  return (
    <span
      ref={ref}
      role={role}
      className={classNames(
        "inline-flex w-fit items-center gap-ui-1 rounded-[var(--radius-round)] px-ui-2 py-ui-1 text-caption font-semibold",
        variantClasses[variant],
        className,
      )}
      {...props}
    >
      {icon && <span aria-hidden="true">{icon}</span>}
      {children}
    </span>
  );
});
