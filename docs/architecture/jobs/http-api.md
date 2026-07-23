# Jobs HTTP API

The versioned Jobs API is a transport adapter over the authoritative command and
query services. Authentication and permission resolution use the security session;
the router receives an immutable `AuthorizationContext` and a distinct application
session. `JobService` owns mutation transactions and Business Event staging.
`JobsQueryService` derives Company and authorized-Branch scope. Routers do not query
repositories, open transactions, or reproduce lifecycle and filtering rules.

## Endpoints and permissions

- `GET /api/v1/jobs` and `GET /api/v1/jobs/{job_id}` require `COMPANY_JOB_READ`.
- Creation, activation, cancellation, and reopening require `COMPANY_JOB_MANAGE`.
- Start, pause, resume, and completion require `COMPANY_JOB_EXECUTE`.

This split is deliberately non-hierarchical. `READ` permits viewing Jobs only;
`MANAGE` represents office and supervisory control over creation and the administrative
lifecycle; `EXECUTE` permits field-work lifecycle actions. A CSR or Dispatcher can be
given management without field execution, while a future Technician can execute
assigned work without receiving broad management authority. Assignment and Dispatch
authorization remain separate future boundaries; this milestone does not determine
which Jobs a Technician may execute.

| Endpoint | Permission |
| --- | --- |
| `GET /api/v1/jobs` | `COMPANY_JOB_READ` |
| `GET /api/v1/jobs/{job_id}` | `COMPANY_JOB_READ` |
| `POST /api/v1/jobs` | `COMPANY_JOB_MANAGE` |
| `POST /api/v1/jobs/from-appointment` | `COMPANY_JOB_MANAGE` |
| `POST /api/v1/jobs/{job_id}/activate` | `COMPANY_JOB_MANAGE` |
| `POST /api/v1/jobs/{job_id}/cancel` | `COMPANY_JOB_MANAGE` |
| `POST /api/v1/jobs/{job_id}/reopen` | `COMPANY_JOB_MANAGE` |
| `POST /api/v1/jobs/{job_id}/start` | `COMPANY_JOB_EXECUTE` |
| `POST /api/v1/jobs/{job_id}/pause` | `COMPANY_JOB_EXECUTE` |
| `POST /api/v1/jobs/{job_id}/resume` | `COMPANY_JOB_EXECUTE` |
| `POST /api/v1/jobs/{job_id}/complete` | `COMPANY_JOB_EXECUTE` |

The canonical permission catalog contains these records. Fresh bootstrap follows the
existing initial-administrator policy. Existing installations must explicitly run the
permission-catalog synchronization operation, then assign permissions through Company
Administration. Synchronization does not alter existing Roles. Authorization-version
invalidation and reauthentication continue to apply after assignment.

## Query contract

The list endpoint maps typed query parameters into `JobSearchQuery`. It supports
Branch, lifecycle, priority, Job type, exact Job number, Customer, Service Location,
Appointment, six half-open date ranges, historical terminal facts, Appointment
presence, operational search, controlled sorting, and bounded offset pagination.
Company and authorized-Branch scope are never accepted from HTTP input.

## Mutation contract

Creation returns `201`. Lifecycle operations accept `expected_version`; pause,
cancellation, and reopening additionally accept their controlled reason enums. The
response represents persisted Job state, including nullable lifecycle timestamps and
retained historical completion or cancellation attribution.

`POST /api/v1/jobs/from-appointment` accepts an Appointment identifier plus optional
Job metadata. The Jobs service derives Branch, Customer, and Service Location from the
locked Scheduling reference, creates the Job and durable association atomically, and
returns the persisted Job. Identical retries return that Job without duplicate events;
a conflicting existing association returns `409`.

## Errors and concealment

- `401`: authentication required.
- `403`: required Jobs permission is absent.
- `404`: missing, cross-Company, or inaccessible-Branch resource.
- `409`: stale version, invalid transition, guard rejection, or link conflict.
- `422`: malformed transport input or controlled domain/query validation.

Responses never include SQL, raw exceptions, or tenant-existence details.
Authentication and endpoint permission checks occur before Jobs are loaded: an
unauthenticated caller receives `401`, and an authenticated caller without the exact
endpoint permission receives `403`. Only after those checks does Jobs-owned Company
and Branch concealment produce `404` for missing or inaccessible records. Malformed
transport input produces `422`.
