import type { JobStatus } from "../../types/jobs";

export const operationalJobStatuses = ["draft", "ready", "in_progress", "paused"] as const satisfies readonly JobStatus[];

const deviceTimeZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone;

function offsetAt(instant: Date, timeZone: string): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(instant);
  const value = (type: string) =>
    Number(parts.find((part) => part.type === type)?.value);
  return (
    Date.UTC(
      value("year"),
      value("month") - 1,
      value("day"),
      value("hour"),
      value("minute"),
      value("second"),
    ) - instant.getTime()
  );
}

function zonedMidnight(dateValue: string, timeZone: string): Date {
  const [year, month, day] = dateValue.split("-").map(Number);
  const civil = Date.UTC(year, month - 1, day);
  let start = new Date(civil - offsetAt(new Date(civil), timeZone));
  start = new Date(civil - offsetAt(start, timeZone));
  return start;
}

export function zonedDateTimeInput(value: string, timeZone: string): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(value));
  const part = (type: string) =>
    parts.find((item) => item.type === type)?.value;
  return `${part("year")}-${part("month")}-${part("day")}T${part("hour")}:${part("minute")}`;
}

export function zonedDateTimeToIso(value: string, timeZone: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!match) throw new Error("Local date-time is invalid.");
  const [, year, month, day, hour, minute] = match.map(Number);
  const civil = Date.UTC(year, month - 1, day, hour, minute);
  let instant = new Date(civil - offsetAt(new Date(civil), timeZone));
  instant = new Date(civil - offsetAt(instant, timeZone));
  return instant.toISOString();
}

export function dayRange(
  dateValue: string,
  timeZone = deviceTimeZone(),
): { startAt: string; endAt: string } {
  const start = zonedMidnight(dateValue, timeZone);
  const end = zonedMidnight(moveDate(dateValue, 1), timeZone);
  return { startAt: start.toISOString(), endAt: end.toISOString() };
}

export function localDateValue(
  date: Date,
  timeZone = deviceTimeZone(),
): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const value = (type: string) =>
    parts.find((part) => part.type === type)?.value;
  return `${value("year")}-${value("month")}-${value("day")}`;
}

export function moveDate(dateValue: string, days: number): string {
  const [year, month, day] = dateValue.split("-").map(Number);
  const moved = new Date(Date.UTC(year, month - 1, day + days));
  return `${moved.getUTCFullYear()}-${String(moved.getUTCMonth() + 1).padStart(2, "0")}-${String(moved.getUTCDate()).padStart(2, "0")}`;
}
