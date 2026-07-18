export type LayoutSpace = "none" | "xsmall" | "small" | "medium" | "large" | "xlarge";
export type LayoutAlignment = "start" | "center" | "end" | "stretch";

export const spaceClasses: Record<LayoutSpace, string> = {
  none: "gap-ui-0",
  xsmall: "gap-ui-1",
  small: "gap-ui-2",
  medium: "gap-ui-4",
  large: "gap-ui-6",
  xlarge: "gap-ui-8",
};

export const alignmentClasses: Record<LayoutAlignment, string> = {
  start: "items-start",
  center: "items-center",
  end: "items-end",
  stretch: "items-stretch",
};
