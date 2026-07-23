import type { JobStatus } from "../../types/jobs";

export const operationalJobStatuses = ["draft", "ready", "in_progress", "paused"] as const satisfies readonly JobStatus[];

export function dayRange(dateValue: string): { startAt: string; endAt: string } {
  const [year, month, day] = dateValue.split("-").map(Number);
  const start = new Date(year, month - 1, day);
  const end = new Date(year, month - 1, day + 1);
  return { startAt: start.toISOString(), endAt: end.toISOString() };
}

export function localDateValue(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function moveDate(dateValue: string, days: number): string {
  const [year, month, day] = dateValue.split("-").map(Number);
  return localDateValue(new Date(year, month - 1, day + days));
}
