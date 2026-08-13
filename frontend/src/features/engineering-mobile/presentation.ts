export function mobileEngineeringLabel(value: string): string {
  return value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function milestoneDisplayStatus(item: {
  status: string;
  attention_reason: string;
  available_owner_actions: readonly string[];
}): string {
  return item.available_owner_actions.includes("request_revision")
    && item.attention_reason.includes("Revision available")
    ? "Validation Failed"
    : mobileEngineeringLabel(item.status);
}

export function mobileEngineeringTimestamp(value: string | null): string {
  if (!value) return "Not available";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function shortExpectedHead(value: string): string {
  return value.slice(0, 8);
}

export function mobileEngineeringRelativeTime(value: string | null, now = Date.now()): string {
  if (!value) return "No signal received";
  const seconds = Math.max(0, Math.round((now - new Date(value).getTime()) / 1000));
  if (seconds < 10) return "Just now";
  if (seconds < 60) return `${seconds} seconds ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.round(minutes / 60);
  return `${hours} hour${hours === 1 ? "" : "s"} ago`;
}

export function workstreamDisplayName(displayName: string, fallback: string): string {
  const normalized = displayName.trim();
  return normalized || fallback;
}
