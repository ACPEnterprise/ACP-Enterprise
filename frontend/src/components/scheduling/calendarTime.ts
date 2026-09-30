const formatters = new Map<string, Intl.DateTimeFormat>();

const parts = (value: Date, timeZone: string) => {
  let formatter = formatters.get(timeZone);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat("en-CA", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    });
    formatters.set(timeZone, formatter);
  }
  const result = formatter.formatToParts(value);
  return Object.fromEntries(result.map((item) => [item.type, item.value]));
};

export const calendarDateKey = (value: Date | string, timeZone: string) => {
  const item = parts(typeof value === "string" ? new Date(value) : value, timeZone);
  return `${item.year}-${item.month}-${item.day}`;
};

export const calendarMinute = (value: string, timeZone: string) => {
  const item = parts(new Date(value), timeZone);
  return Number(item.hour) * 60 + Number(item.minute);
};

export const calendarTimeLabel = (value: string | null, timeZone: string) =>
  value
    ? new Date(value).toLocaleTimeString([], {
        timeZone,
        hour: "numeric",
        minute: "2-digit",
      })
    : "Time unknown";

/** Resolve a Branch-local wall time to an instant without assuming device timezone. */
export const branchLocalInstant = (
  dateKey: string,
  minute: number,
  timeZone: string,
) => {
  const [year, month, day] = dateKey.split("-").map(Number);
  const hour = Math.floor(minute / 60);
  const localMinute = minute % 60;
  const desired = Date.UTC(year, month - 1, day, hour, localMinute);
  let instant = desired;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const observed = parts(new Date(instant), timeZone);
    const observedAsUtc = Date.UTC(
      Number(observed.year),
      Number(observed.month) - 1,
      Number(observed.day),
      Number(observed.hour),
      Number(observed.minute),
    );
    instant += desired - observedAsUtc;
  }
  const result = new Date(instant);
  if (
    calendarDateKey(result, timeZone) !== dateKey ||
    calendarMinute(result.toISOString(), timeZone) !== minute
  ) {
    throw new Error("The selected Branch-local time does not exist.");
  }
  return result;
};

export const branchLocalInput = (value: string | null, timeZone: string) => {
  if (!value) return "";
  const item = parts(new Date(value), timeZone);
  return `${item.year}-${item.month}-${item.day}T${item.hour}:${item.minute}`;
};

export const branchInputInstant = (value: string, timeZone: string) => {
  const [dateKey, clock] = value.split("T");
  const [hour, minute] = clock.split(":").map(Number);
  return branchLocalInstant(dateKey, hour * 60 + minute, timeZone);
};
