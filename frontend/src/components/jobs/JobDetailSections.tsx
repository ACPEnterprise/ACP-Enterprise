import type { JobDetail } from "../../types/jobs";
import { Card } from "../../ui";

export function CustomerSummaryCard({ job }: { readonly job: JobDetail }) {
  return <Card className="p-ui-6"><h3 className="font-semibold">Customer</h3><p className="mt-2">{job.customer.display_name}</p><p className="text-sm text-slate-500">{job.customer.customer_number}</p></Card>;
}
export function ServiceLocationCard({ job }: { readonly job: JobDetail }) {
  const location = job.service_location;
  return <Card className="p-ui-6"><h3 className="font-semibold">Service Location</h3><address className="mt-2 not-italic text-sm text-slate-300">{location.nickname && <strong className="block">{location.nickname}</strong>}{location.address_line_1}<br />{location.address_line_2 && <>{location.address_line_2}<br /></>}{location.city}, {location.state} {location.postal_code}</address></Card>;
}
export function AppointmentSummaryTable({ job }: { readonly job: JobDetail }) {
  return <Card className="p-ui-6"><h3 className="font-semibold">Appointments</h3>{job.appointments.length === 0 ? <p className="mt-3 text-sm text-slate-500">No Appointments linked.</p> : <div className="mt-3 divide-y divide-slate-800">{job.appointments.map((item) => <div className="flex justify-between py-3 text-sm" key={item.appointment_id}><span>{item.visit_sequence}. {item.appointment_number}</span><span className="text-slate-400">{item.arrival_window_start_at ? new Date(item.arrival_window_start_at).toLocaleString() : item.status}</span></div>)}</div>}</Card>;
}
