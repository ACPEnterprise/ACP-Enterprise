# Jobs Frontend Foundation

Jobs follows the application-shell route, React Query, typed API-client, and backend
HTTP architecture. `/jobs` renders the operational list and `/jobs/:jobId` renders a
detail projection. Both routes remain protected by the shared authentication shell.

Transport types in `src/types/jobs.ts` mirror HTTP payloads rather than backend ORM or
domain types. `src/api/jobs.ts` owns the `/api/v1/jobs` URL family; components never
call `fetch` or construct endpoint paths. `src/hooks/useJobs.ts` owns query keys,
queries, lifecycle mutations, and targeted invalidation of Jobs lists plus the changed
Job detail.

The list owns only filter controls for search, status, priority, Job type, Branch,
sorting, and pagination. These controls compose API requests; filtering, authorization,
and lifecycle behavior remain server-owned. The detail route composes lifecycle,
Customer, Service Location, and Appointment components from the live detail response.
Lifecycle actions submit the displayed concurrency version and render controlled API
errors without duplicating transition rules.

Server state belongs to React Query. Components retain only transient input, filter,
page, and error-display state. Loading, empty, and failure states reuse ACP UI
primitives. Future Dispatch, technician assignment, timeline, forms, and financial
views extend these typed seams after their bounded contexts are approved; this
foundation contains no placeholders or mock production data.
