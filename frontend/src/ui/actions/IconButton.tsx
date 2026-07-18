import {
  forwardRef,
  type ComponentPropsWithoutRef,
  type ReactNode,
} from "react";

import { Spinner } from "../feedback/Spinner";
import { classNames } from "../utilities/classNames";
import type { ButtonSize, ButtonVariant } from "./Button";

export interface IconButtonProps
  extends Omit<ComponentPropsWithoutRef<"button">, "children" | "aria-label"> {
  icon: ReactNode;
  label: string;
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}

const variantClasses: Record<ButtonVariant, string> = {
  primary: "bg-action-primary text-content-inverse hover:bg-action-primary-hover",
  secondary: "bg-action-secondary text-content hover:brightness-110",
  outline: "border-stroke-strong bg-transparent text-content hover:bg-surface-muted",
  ghost: "bg-transparent text-content-secondary hover:bg-surface-muted hover:text-content",
  destructive: "bg-status-danger text-content-inverse hover:brightness-110",
};

const sizeClasses: Record<ButtonSize, string> = {
  small: "size-10 [&_svg]:size-[var(--icon-small)]",
  medium: "size-11 [&_svg]:size-[var(--icon-medium)]",
  large: "size-12 [&_svg]:size-[var(--icon-large)]",
};

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  function IconButton(
    {
      className,
      disabled,
      icon,
      label,
      loading = false,
      size = "medium",
      type = "button",
      variant = "ghost",
      ...props
    },
    ref,
  ) {
    return (
      <button
        ref={ref}
        type={type}
        disabled={disabled || loading}
        aria-label={label}
        aria-busy={loading || undefined}
        className={classNames(
          "inline-flex shrink-0 items-center justify-center rounded-md border border-transparent transition-colors [transition-duration:var(--duration-fast)] disabled:cursor-not-allowed disabled:bg-[var(--semantic-disabled-background)] disabled:text-[var(--semantic-disabled-content)]",
          variantClasses[variant],
          sizeClasses[size],
          className,
        )}
        {...props}
      >
        {loading ? (
          <Spinner decorative size="small" />
        ) : (
          <span aria-hidden="true" className="inline-flex">
            {icon}
          </span>
        )}
      </button>
    );
  },
);
