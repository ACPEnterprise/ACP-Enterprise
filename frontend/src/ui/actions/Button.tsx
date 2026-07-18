import {
  forwardRef,
  type ComponentPropsWithoutRef,
  type ReactNode,
} from "react";

import { VisuallyHidden } from "../accessibility/VisuallyHidden";
import { Spinner } from "../feedback/Spinner";
import { classNames } from "../utilities/classNames";

export type ButtonVariant =
  | "primary"
  | "secondary"
  | "outline"
  | "ghost"
  | "destructive";
export type ButtonSize = "small" | "medium" | "large";

export interface ButtonProps
  extends Omit<ComponentPropsWithoutRef<"button">, "children"> {
  children: ReactNode;
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  loadingLabel?: string;
  leadingIcon?: ReactNode;
  trailingIcon?: ReactNode;
  fullWidth?: boolean;
}

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    "border-transparent bg-action-primary text-content-inverse hover:bg-action-primary-hover active:bg-action-primary-active",
  secondary:
    "border-transparent bg-action-secondary text-content hover:brightness-110 active:brightness-95",
  outline:
    "border-stroke-strong bg-transparent text-content hover:bg-surface-muted active:bg-surface-raised",
  ghost:
    "border-transparent bg-transparent text-content-secondary hover:bg-surface-muted hover:text-content active:bg-surface-raised",
  destructive:
    "border-transparent bg-status-danger text-content-inverse hover:brightness-110 active:brightness-90",
};

const sizeClasses: Record<ButtonSize, string> = {
  small: "min-h-10 gap-ui-2 px-ui-3 text-body-s",
  medium: "min-h-11 gap-ui-2 px-ui-4 text-body-s",
  large: "min-h-12 gap-ui-3 px-ui-5 text-body",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    children,
    className,
    disabled,
    fullWidth = false,
    leadingIcon,
    loading = false,
    loadingLabel = "Loading",
    size = "medium",
    trailingIcon,
    type = "button",
    variant = "primary",
    ...props
  },
  ref,
) {
  const unavailable = disabled || loading;
  return (
    <button
      ref={ref}
      type={type}
      disabled={unavailable}
      aria-busy={loading || undefined}
      className={classNames(
        "inline-flex items-center justify-center rounded-md border font-semibold transition-colors [transition-duration:var(--duration-fast)] disabled:cursor-not-allowed disabled:bg-[var(--semantic-disabled-background)] disabled:text-[var(--semantic-disabled-content)] disabled:opacity-100",
        variantClasses[variant],
        sizeClasses[size],
        fullWidth && "w-full",
        className,
      )}
      {...props}
    >
      {loading ? (
        <Spinner decorative size="small" />
      ) : leadingIcon ? (
        <span aria-hidden="true" className="inline-flex shrink-0">
          {leadingIcon}
        </span>
      ) : null}
      <span>{children}</span>
      {loading && (
        <>
          {" "}
          <VisuallyHidden>{loadingLabel}</VisuallyHidden>
        </>
      )}
      {!loading && trailingIcon && (
        <span aria-hidden="true" className="inline-flex shrink-0">
          {trailingIcon}
        </span>
      )}
    </button>
  );
});
