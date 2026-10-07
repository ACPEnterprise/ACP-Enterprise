const TECHNICIAN_COLORS = [
  { background: "#D9F0ED", border: "#087A70", text: "#174B47" },
  { background: "#F4DDE2", border: "#8C2940", text: "#602031" },
  { background: "#E9E0F5", border: "#70459A", text: "#4D306C" },
  { background: "#F8EBC8", border: "#9A6A00", text: "#634700" },
  { background: "#DDE8F6", border: "#356A9A", text: "#244B6D" },
  { background: "#E2EBD6", border: "#527A30", text: "#385522" },
] as const;

export const UNASSIGNED_COLOR = {
  background: "#F7E2D4",
  border: "#B54708",
  text: "#6E2C00",
} as const;

export function technicianCalendarColor(employeeId: string) {
  if (employeeId === "__unassigned") return UNASSIGNED_COLOR;
  let hash = 2166136261;
  for (const character of employeeId) {
    hash ^= character.codePointAt(0) ?? 0;
    hash = Math.imul(hash, 16777619);
  }
  return TECHNICIAN_COLORS[Math.abs(hash) % TECHNICIAN_COLORS.length];
}

export const humanWorkLabel = (customer: string | null | undefined) =>
  customer?.trim() || "Customer unavailable";

export const humanServiceLabel = (service: string | null | undefined) =>
  service?.trim().replaceAll("_", " ") || "Service visit";
