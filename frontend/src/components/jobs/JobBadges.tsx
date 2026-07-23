import { Badge } from "../../ui";
import type { JobPriority, JobStatus } from "../../types/jobs";
import { statusLabels } from "./jobPresentation";

export function JobStatusBadge({ status }: { readonly status: JobStatus }) {
  const variant = status === "completed" ? "success" : status === "cancelled" ? "danger" : status === "paused" ? "warning" : "information";
  return <Badge variant={variant}>{statusLabels[status]}</Badge>;
}
export function JobPriorityBadge({ priority }: { readonly priority: JobPriority }) {
  const variant = priority === "emergency" ? "danger" : priority === "urgent" || priority === "high" ? "warning" : "neutral";
  return <Badge variant={variant}>{priority}</Badge>;
}
