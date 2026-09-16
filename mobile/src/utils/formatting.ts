/**
 * Format an authoritative timestamp without allowing malformed timezone data
 * to crash the employee app. A bad timezone is surfaced as the server value;
 * it is never silently reinterpreted as device-local or guessed UTC time.
 */
export function formatAuthoritativeTimestamp(
  value: string,
  timezone: string | undefined,
  options: Intl.DateTimeFormatOptions,
): string {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return value;
  try {
    return new Intl.DateTimeFormat(undefined, {
      ...options,
      ...(timezone ? { timeZone: timezone } : {}),
    }).format(date);
  } catch {
    return value;
  }
}

export function formatAuthoritativeDate(value: string): string {
  return formatAuthoritativeTimestamp(`${value}T12:00:00Z`, "UTC", {
    dateStyle: "full",
  });
}
