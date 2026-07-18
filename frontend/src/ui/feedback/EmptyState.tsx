import {
  forwardRef,
  useId,
  type ComponentPropsWithoutRef,
  type ReactNode,
} from "react";

import { classNames } from "../utilities/classNames";

export interface EmptyStateProps
  extends Omit<ComponentPropsWithoutRef<"section">, "title"> {
  icon?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  primaryAction?: ReactNode;
  secondaryAction?: ReactNode;
}

export const EmptyState = forwardRef<HTMLElement, EmptyStateProps>(
  function EmptyState(
    {
      className,
      description,
      icon,
      primaryAction,
      secondaryAction,
      title,
      ...props
    },
    ref,
  ) {
    const titleId = useId();
    return (
      <section
        ref={ref}
        aria-labelledby={titleId}
        className={classNames(
          "flex flex-col items-center rounded-xl border border-dashed border-stroke p-ui-8 text-center",
          className,
        )}
        {...props}
      >
        {icon && (
          <span aria-hidden="true" className="mb-ui-4 text-content-muted [&_svg]:size-[var(--icon-xlarge)]">
            {icon}
          </span>
        )}
        <h2 id={titleId} className="text-heading-s text-content">{title}</h2>
        {description && <div className="mt-ui-2 max-w-[var(--content-compact)] text-body-s text-content-muted">{description}</div>}
        {(primaryAction || secondaryAction) && (
          <div className="mt-ui-5 flex flex-wrap justify-center gap-ui-2">
            {primaryAction}
            {secondaryAction}
          </div>
        )}
      </section>
    );
  },
);
