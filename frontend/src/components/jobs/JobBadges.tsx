import { Badge } from "../../ui";
import type { JobPriority, JobStatus } from "../../types/jobs";

export function JobStatusBadge({ status }: { readonly status: JobStatus }) {
  const variant = status === "completed" ? "success" : status === "cancelled" ? "danger" : status === "paused" ? "warning" : "information";
  return <Badge variant={variant}>{status.replaceAll("_", " ")}</Badge>;
}
export function JobPriorityBadge({ priority }: { readonly priority: JobPriority }) {
  const variant = priority === "emergency" ? "danger" : priority === "urgent" || priority === "high" ? "warning" : "neutral";
  return <Badge variant={variant}>{priority}</Badge>;
}
