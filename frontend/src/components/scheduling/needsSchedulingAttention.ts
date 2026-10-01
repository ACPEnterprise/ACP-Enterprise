import type { DispatchBoardItem } from "../../types/dispatch";
import type { JobListItem, JobPriority, JobStatus } from "../../types/jobs";
import type { AppointmentDetail } from "../../types/scheduling";

const hasActiveAssignment = (item?: DispatchBoardItem) =>
  Boolean(
    item?.assignment &&
      !["released", "replaced", "cancelled"].includes(item.assignment.status),
  );

export function needsSchedulingAttentionCount(props: {
  readonly jobs: readonly JobListItem[];
  readonly appointments: readonly AppointmentDetail[];
  readonly dispatchByAppointment: ReadonlyMap<string, DispatchBoardItem>;
  readonly jobsById: ReadonlyMap<string, JobListItem>;
  readonly search: string;
  readonly serviceCategory: string;
  readonly jobStatus: JobStatus | "";
  readonly priority: JobPriority | "";
}) {
  const search = props.search.trim().toLowerCase();
  const matchesJob = (job?: JobListItem) =>
    Boolean(
      job &&
        (!props.jobStatus || job.status === props.jobStatus) &&
        (!props.priority || job.priority === props.priority) &&
        (!props.serviceCategory ||
          job.job_type_code === props.serviceCategory) &&
        (!search ||
          `${job.job_number} ${job.customer_display_name} ${job.service_location_label}`
            .toLowerCase()
            .includes(search)),
    );
  const unscheduled = props.jobs.filter(
    (job) => !job.earliest_appointment_start_at && matchesJob(job),
  ).length;
  const appointmentAttention = props.appointments.filter((appointment) => {
    const dispatch = props.dispatchByAppointment.get(appointment.id);
    const scheduled =
      appointment.status !== "draft" && appointment.arrival_window_start_at;
    if (scheduled && hasActiveAssignment(dispatch)) return false;
    const job = dispatch?.job_id
      ? props.jobsById.get(dispatch.job_id)
      : undefined;
    return job
      ? matchesJob(job)
      : !props.jobStatus &&
          !props.priority &&
          (!search ||
            appointment.appointment_number.toLowerCase().includes(search));
  }).length;
  return unscheduled + appointmentAttention;
}
