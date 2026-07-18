import { forwardRef, type ComponentPropsWithoutRef } from "react";

import { classNames } from "../utilities/classNames";
import { alignmentClasses, spaceClasses, type LayoutAlignment, type LayoutSpace } from "./types";

export type ClusterJustification = "start" | "center" | "end" | "between";
export interface ClusterProps extends ComponentPropsWithoutRef<"div"> {
  space?: LayoutSpace;
  align?: LayoutAlignment;
  justify?: ClusterJustification;
}

const justificationClasses: Record<ClusterJustification, string> = {
  start: "justify-start",
  center: "justify-center",
  end: "justify-end",
  between: "justify-between",
};

export const Cluster = forwardRef<HTMLDivElement, ClusterProps>(function Cluster(
  { align = "center", className, justify = "start", space = "small", ...props },
  ref,
) {
  return <div ref={ref} className={classNames("flex flex-row flex-wrap", spaceClasses[space], alignmentClasses[align], justificationClasses[justify], className)} {...props} />;
});
