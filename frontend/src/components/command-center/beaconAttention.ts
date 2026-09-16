import type { BeaconSignal } from "../../api/beacon";

export type AttentionWindow = "NOW" | "TODAY" | "THIS WEEK" | "WATCH";

export const attentionWindows: readonly AttentionWindow[] = [
  "NOW",
  "TODAY",
  "THIS WEEK",
  "WATCH",
];

export function attentionWindow(signal: BeaconSignal): AttentionWindow {
  if (
    signal.severity === "critical" ||
    signal.priority.band === "critical" ||
    signal.priority.band === "immediate"
  ) return "NOW";
  if (
    signal.severity === "important" ||
    signal.priority.band === "important"
  ) return "TODAY";
  if (signal.severity === "attention") return "THIS WEEK";
  return "WATCH";
}
