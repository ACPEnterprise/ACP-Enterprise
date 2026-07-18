import {
  forwardRef,
  useId,
  type ComponentPropsWithoutRef,
  type ReactNode,
} from "react";

import { classNames } from "../utilities/classNames";

export type AlertVariant = "information" | "success" | "warning" | "danger";
export type AlertAnnouncement = "polite" | "assertive";
export interface AlertProps extends Omit<ComponentPropsWithoutRef<"div">, "title"> {
  variant?: AlertVariant;
  title?: ReactNode;
  icon?: ReactNode;
  action?: ReactNode;
  announcement?: AlertAnnouncement;
}

const variantClasses: Record<AlertVariant, string> = {
  information: "border-status-information/40 bg-status-information/10 text-status-information",
  success: "border-status-success/40 bg-status-success/10 text-status-success",
  warning: "border-status-warning/40 bg-status-warning/10 text-status-warning",
  danger: "border-status-danger/40 bg-status-danger/10 text-status-danger",
};

export const Alert = forwardRef<HTMLDivElement, AlertProps>(function Alert(
  {
    action,
    announcement,
    children,
    className,
    icon,
    title,
    variant = "information",
    ...props
  },
  ref,
) {
  const titleId = useId();
  return (
    <div
      ref={ref}
      role={announcement === "assertive" ? "alert" : announcement ? "status" : undefined}
      aria-live={announcement}
      aria-labelledby={title ? titleId : undefined}
      className={classNames(
        "flex gap-ui-3 rounded-lg border p-ui-4 text-body-s",
        variantClasses[variant],
        className,
      )}
      {...props}
    >
      {icon && <span aria-hidden="true" className="mt-ui-1 shrink-0">{icon}</span>}
      <div className="min-w-0 flex-1">
        {title && <p id={titleId} className="font-semibold text-content">{title}</p>}
        <div className={classNames("text-content-secondary", Boolean(title) && "mt-ui-1")}>{children}</div>
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
});
