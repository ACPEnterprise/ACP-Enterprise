import type { JobListItem } from "../../types/jobs";
import { Card } from "../../ui";

export function DispatchSummary({ appointmentTotal, jobTotal, visibleJobs }: { readonly appointmentTotal: number; readonly jobTotal: number; readonly visibleJobs: readonly JobListItem[] }) {
  const scheduled = visibleJobs.filter(
    (job) => Boolean(job.earliest_appointment_start_at),
  ).length;
  const unscheduled = visibleJobs.filter(
    (job) => !job.earliest_appointment_start_at,
  ).length;
  const values = [
    ["Appointments", appointmentTotal, "selected scope"],
    ["Operational Jobs", jobTotal, "selected Branch scope"],
    ["Scheduled", scheduled, "visible Jobs"],
    ["Unscheduled", unscheduled, "visible Jobs"],
  ] as const;
  return <section aria-label="Dispatch summary" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{values.map(([label, value, qualifier]) => <Card className="p-ui-4" key={label}><p className="text-sm text-content-muted">{label}</p><p className="mt-1 text-2xl font-bold">{value}</p><p className="mt-1 text-xs text-content-muted">{qualifier}</p></Card>)}</section>;
}
