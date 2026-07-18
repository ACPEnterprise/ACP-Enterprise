import { forwardRef, type ComponentPropsWithoutRef } from "react";

import { classNames } from "../utilities/classNames";
import { spaceClasses, type LayoutSpace } from "./types";

export type InlineAlignment = "start" | "center" | "end" | "baseline" | "stretch";
export interface InlineProps extends ComponentPropsWithoutRef<"div"> {
  space?: LayoutSpace;
  align?: InlineAlignment;
}

const alignmentClasses: Record<InlineAlignment, string> = {
  start: "items-start",
  center: "items-center",
  end: "items-end",
  baseline: "items-baseline",
  stretch: "items-stretch",
};

export const Inline = forwardRef<HTMLDivElement, InlineProps>(function Inline(
  { align = "center", className, space = "small", ...props },
  ref,
) {
  return <div ref={ref} className={classNames("flex flex-row flex-nowrap", spaceClasses[space], alignmentClasses[align], className)} {...props} />;
});
