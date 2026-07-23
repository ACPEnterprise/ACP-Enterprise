# Appointment-to-Job Operational Integration

## Authoritative relationship

Scheduling owns Appointment lifecycle, timing, Branch, Customer, and Service Location facts. Jobs owns Job creation, execution lifecycle, numbering, and `job_appointment_links`. The UI recognizes a relationship only through that durable Jobs-owned association; matching names, addresses, or dates never implies a link.

Jobs exposes `POST /api/v1/jobs/from-appointment`. The request identifies the source Appointment and contains only optional Job metadata. `JobService.create_job_from_appointment` locks and validates the Appointment, enforces Company and authorized-Branch scope, validates Customer and Service Location consistency, and applies the initial one-Job-per-Appointment policy. The transaction creates the Job and link and stages `job.created` and `job.appointment_linked` with one operation timestamp and correlation ID. An identical retry returns the existing Job without duplicate events; a conflicting relationship returns `409`.

The Appointment workspace resolves its relationship through the existing Jobs query filter `appointment_id`. This keeps relationship SQL and concealment in Jobs. Scheduling responses are not extended with Jobs-owned state. Job detail already includes immutable Appointment summaries from the Jobs query engine.

## Frontend flow

`/appointments/:appointmentId` loads Appointment detail through the Scheduling query key and loads its related Job through a separate Jobs query key. Eligible unlinked Appointments may open a review form that submits only optional Job metadata. Branch, Customer, and Service Location are taken from the Appointment by the backend, not copied from editable browser inputs.

Successful creation invalidates the source Appointment detail, all Jobs lists (including the Appointment relationship lookup), and the returned Job detail before navigating to `/jobs/:jobId`. A conflict invalidates the Appointment and relationship queries so an existing authoritative Job can replace the creation UI when it becomes visible.

Job detail links each authoritative Appointment summary to `/appointments/:appointmentId`. Business numbers are the primary navigation labels in both directions.

## Permissions and concealment

Appointment detail requires Scheduling read authority. Relationship lookup requires Jobs read authority. Creation requires Jobs manage authority. The current browser authentication snapshot does not contain resolved permission codes, so action visibility is lifecycle guidance rather than an authorization boundary; the backend remains authoritative and safely returns `403`. Missing, cross-company, and inaccessible Branch resources retain existing `404` concealment behavior.

## Errors and limitations

Known authentication, authorization, concealment, validation, and conflict responses are not automatically retried. Transient failures use the shared bounded retry policy. Operator messages do not expose internal exceptions or database details.

Appointments currently contain no service-summary or description field, so the create form does not synthesize one. Operators may enter optional Job problem and internal-description metadata. The initial Appointment page is a direct-detail workspace reached from linked Jobs or a direct URL; a Scheduling calendar frontend remains deferred.

Dispatch, technician assignment, routing, estimates, invoices, payments, inventory, time tracking, payroll, accounting, and Job costing remain separate future integrations.
