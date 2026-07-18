import { forwardRef, type ComponentPropsWithoutRef } from "react";

import { classNames } from "../utilities/classNames";
import { alignmentClasses, spaceClasses, type LayoutAlignment, type LayoutSpace } from "./types";

export interface StackProps extends ComponentPropsWithoutRef<"div"> {
  space?: LayoutSpace;
  align?: LayoutAlignment;
}

export const Stack = forwardRef<HTMLDivElement, StackProps>(function Stack(
  { align = "stretch", className, space = "medium", ...props },
  ref,
) {
  return <div ref={ref} className={classNames("flex flex-col", spaceClasses[space], alignmentClasses[align], className)} {...props} />;
});
