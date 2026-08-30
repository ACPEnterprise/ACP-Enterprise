import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";

import { getOperatorApiError } from "../api/errors";
import { CreateJobFromAppointmentPanel } from "../components/appointments/CreateJobFromAppointmentPanel";
import { AppointmentLifecycleControls } from "../components/appointments/AppointmentLifecycleControls";
import { useAuth, useHasPermission } from "../auth";
import { useCustomerDetail } from "../hooks/useCustomers";
import { useJobForAppointment } from "../hooks/useJobs";
import { useAppointment } from "../hooks/useScheduling";
import { jobDetailPath, schedulingPath } from "../routing/paths";
import { Alert, Button, Card } from "../ui";

const jobEligibleStatuses = new Set(["draft", "scheduled", "confirmed", "completed"]);
const displayStatus = (value: string) => value.replaceAll("_", " ");
const timestamp = (value: string | null) => value ? new Date(value).toLocaleString() : "Not scheduled";

export function AppointmentDetailRoute() {
  const { appointmentId } = useParams();
  const appointmentQuery = useAppointment(appointmentId);
  const relatedQuery = useJobForAppointment(appointmentId);
  const [creating, setCreating] = useState(false);
  const { activeCompany } = useAuth();
  const canManageSchedule = useHasPermission("COMPANY_SCHEDULING_MANAGE");
  const appointment = appointmentQuery.data;
  const customerQuery = useCustomerDetail(appointment?.customer_id ?? null);
  if (appointmentQuery.isLoading) return <Card className="p-ui-6"><p>Loading Appointment…</p></Card>;
  if (appointmentQuery.isError || !appointment) {
    const error = getOperatorApiError(appointmentQuery.error, "Appointment");
    return <Alert variant="danger" title={error.title} action={error.retryable ? <Button onClick={() => void appointmentQuery.refetch()}>Retry</Button> : undefined}>{error.message}</Alert>;
  }
  const relatedJob = relatedQuery.data?.items[0];
  const branch = activeCompany?.branches.find((item) => item.id === appointment.branch_id);
  const customer = customerQuery.data;
  const location = customer?.properties.find((item) => item.id === appointment.service_location_id);
  const eligible = jobEligibleStatuses.has(appointment.status);
  return <div className="min-w-0 space-y-6">
    <Link className="inline-flex min-h-11 items-center gap-2 text-sm text-action-primary" to={schedulingPath()}><ArrowLeft size={16} />Back to Scheduling</Link>
    <header className="min-w-0"><div className="flex min-w-0 flex-wrap items-center gap-3"><h2 className="break-all text-2xl font-bold sm:text-3xl">{appointment.appointment_number}</h2><span className="rounded-full bg-status-information/15 px-3 py-1 text-sm capitalize text-status-information">{displayStatus(appointment.status)}</span></div><p className="mt-2 text-content-muted">Scheduled service details and authoritative Job relationship.</p></header>
    <div className="grid min-w-0 gap-4 lg:grid-cols-2"><Card className="p-ui-4 sm:p-ui-6"><h3 className="font-semibold">Service</h3><dl className="mt-4 grid gap-3 text-sm"><div><dt className="text-content-muted">Branch</dt><dd className="break-words">{branch ? `${branch.name} (${branch.code})` : "Accessible Branch"}</dd></div><div><dt className="text-content-muted">Arrival window</dt><dd className="grid gap-1 sm:block"><time>{timestamp(appointment.arrival_window_start_at)}</time><span aria-hidden="true" className="hidden sm:inline"> – </span><span className="text-content-muted sm:hidden">through</span><time>{timestamp(appointment.arrival_window_end_at)}</time></dd></div><div><dt className="text-content-muted">Expected duration</dt><dd>{appointment.expected_duration_minutes ? `${appointment.expected_duration_minutes} minutes` : "Not specified"}</dd></div></dl></Card><Card className="p-ui-4 sm:p-ui-6"><h3 className="font-semibold">Customer and Service Location</h3><p className="mt-3 break-words">{customer ? customer.business_name || `${customer.first_name ?? ""} ${customer.last_name ?? ""}`.trim() : "Customer details unavailable"}</p><address className="mt-2 break-words not-italic text-sm text-content-muted">{location ? <>{location.address_line_1}{location.address_line_2 && <><br />{location.address_line_2}</>}<br />{location.city}, {location.state} {location.postal_code}</> : "Service Location details unavailable"}</address></Card></div>
    <Card className="p-ui-4 sm:p-ui-6"><h3 className="font-semibold">Related Job</h3>{relatedJob ? <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_auto] sm:items-center"><div className="min-w-0"><Link className="break-all font-semibold text-action-primary hover:underline" to={jobDetailPath(relatedJob.id)}>{relatedJob.job_number}</Link><p className="mt-1 text-sm capitalize text-content-muted">{displayStatus(relatedJob.status)}</p></div><Link className="inline-flex min-h-11 w-full items-center justify-center rounded-md bg-action-primary px-ui-4 text-sm font-semibold text-content-inverse sm:w-auto" to={jobDetailPath(relatedJob.id)}>Open Job</Link></div> : relatedQuery.isLoading ? <p className="mt-3 text-sm text-content-muted">Checking for a related Job…</p> : <div className="mt-3"><p className="text-sm text-content-muted">{relatedQuery.isError ? "Related Job information is unavailable with your current access." : "No Job has been created from this Appointment."}</p>{eligible && <Button className="mt-4 sm:w-auto" fullWidth onClick={() => setCreating(true)}>Create Job</Button>}{!eligible && <p className="mt-3 text-sm">This Appointment state is not eligible for Job creation.</p>}</div>}</Card>
    {canManageSchedule && !["completed", "cancelled", "no_show"].includes(appointment.status) && <AppointmentLifecycleControls appointment={appointment} />}
    {creating && !relatedJob && <CreateJobFromAppointmentPanel appointment={appointment} onCancel={() => setCreating(false)} />}
  </div>;
}
