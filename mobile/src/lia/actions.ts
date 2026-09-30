import type { LiaNavigation } from "../api/lia";

const UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}";

/** Mobile only accepts server-authorized destinations in the Employee surface. */
export function employeeActionDestination(action: LiaNavigation): "my-day" | "jobs" | "time" | null {
  if (!action.available || action.action_category !== "EMPLOYEE_WORKFLOW") return null;
  if (action.internal_path === "/my-day" || action.internal_path === "/my-schedule") return "my-day";
  if (action.internal_path === "/my-time") return "time";
  if (action.internal_path === "/jobs" || new RegExp(`^/jobs/${UUID}$`, "i").test(action.internal_path)) return "jobs";
  return null;
}
