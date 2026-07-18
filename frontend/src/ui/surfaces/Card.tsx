import { forwardRef, type ComponentPropsWithoutRef } from "react";

import { classNames } from "../utilities/classNames";

export type CardElevation = "none" | "low" | "medium";
export interface CardProps extends ComponentPropsWithoutRef<"article"> {
  elevation?: CardElevation;
}

const elevationClasses: Record<CardElevation, string> = {
  none: "shadow-none",
  low: "shadow-sm",
  medium: "shadow-md",
};

export const Card = forwardRef<HTMLElement, CardProps>(function Card(
  { className, elevation = "low", ...props },
  ref,
) {
  return (
    <article
      ref={ref}
      className={classNames(
        "rounded-xl border border-stroke bg-surface text-content",
        elevationClasses[elevation],
        className,
      )}
      {...props}
    />
  );
});

export const CardHeader = forwardRef<HTMLElement, ComponentPropsWithoutRef<"header">>(
  function CardHeader({ className, ...props }, ref) {
    return <header ref={ref} className={classNames("p-ui-6 pb-ui-3", className)} {...props} />;
  },
);

export const CardTitle = forwardRef<HTMLHeadingElement, ComponentPropsWithoutRef<"h3">>(
  function CardTitle({ className, ...props }, ref) {
    return <h3 ref={ref} className={classNames("text-heading-s text-content", className)} {...props} />;
  },
);

export const CardDescription = forwardRef<HTMLParagraphElement, ComponentPropsWithoutRef<"p">>(
  function CardDescription({ className, ...props }, ref) {
    return <p ref={ref} className={classNames("mt-ui-1 text-body-s text-content-muted", className)} {...props} />;
  },
);

export const CardActions = forwardRef<HTMLDivElement, ComponentPropsWithoutRef<"div">>(
  function CardActions({ className, ...props }, ref) {
    return <div ref={ref} className={classNames("flex flex-wrap items-center gap-ui-2", className)} {...props} />;
  },
);

export const CardContent = forwardRef<HTMLDivElement, ComponentPropsWithoutRef<"div">>(
  function CardContent({ className, ...props }, ref) {
    return <div ref={ref} className={classNames("p-ui-6 pt-ui-3", className)} {...props} />;
  },
);

export const CardFooter = forwardRef<HTMLElement, ComponentPropsWithoutRef<"footer">>(
  function CardFooter({ className, ...props }, ref) {
    return <footer ref={ref} className={classNames("border-t border-stroke p-ui-6", className)} {...props} />;
  },
);
