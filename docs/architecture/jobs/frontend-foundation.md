# Jobs Frontend Foundation

Jobs follows the application-shell route, React Query, typed API-client, and backend
HTTP architecture. `/jobs` renders the operational list and `/jobs/:jobId` renders a
detail projection. Both routes remain protected by the shared authentication shell.

Transport types in `src/types/jobs.ts` mirror HTTP payloads rather than backend ORM or
domain types. `src/api/jobs.ts` owns the `/api/v1/jobs` URL family; components never
call `fetch` or construct endpoint paths. `src/hooks/useJobs.ts` owns query keys,
queries, lifecycle mutations, and targeted invalidation of Jobs lists plus the changed
Job detail.

The operational list provides search, status, priority, Job type, authorized Branch,
sorting, server pagination, create access, and deterministic request states. These
controls compose API requests; filtering, authorization, and lifecycle behavior remain
server-owned. Each result links directly to its detail route.

Creation uses existing Customer list/detail APIs and the authenticated Company's Branch
snapshot to select authoritative identifiers. It creates a draft through `useCreateJob`
and navigates to the returned Job. Customer and Service Location creation remain in
Customer Management. The current Customer endpoint is paginated and the initial form
loads its first 100 Customers; searchable selector infrastructure is a deferred
dependency for larger Companies.

The detail workspace composes lifecycle, Customer, Service Location, operational
timestamps, descriptions, and ordered Appointment projections from the live response.
A linked Appointment business number navigates to the protected Appointment detail
workspace. Eligible unlinked Appointments can invoke the Jobs-owned
create-from-Appointment workflow without re-entering Scheduling-owned references; the
full cross-domain contract is documented in
[Appointment-to-Job Operational Integration](appointment-integration.md).
A centralized lifecycle-presentation map selects applicable controls. Pause,
cancellation, and reopening use controlled reason values; completion, cancellation,
and reopening require confirmation. Every action submits the displayed concurrency
version, while backend transitions and permissions remain authoritative.

Server state belongs to React Query. Components retain only transient input, filter,
page, confirmation, and feedback state. Queries do not retry 401, 403, 404, 409, or
422 responses; transient failures receive a bounded retry. Mutations invalidate Jobs
lists and only the changed detail. Operator-safe error presentation distinguishes
authentication, authorization, concealment, validation, conflict, and availability.

Future Dispatch, technician assignment, timeline, Estimates, Invoices, routing, parts,
time tracking, and Job costing extend these typed seams after their bounded contexts
are approved. There are no placeholder panels or mock production records.
