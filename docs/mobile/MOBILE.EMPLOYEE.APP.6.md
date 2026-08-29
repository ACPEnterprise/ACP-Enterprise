# MOBILE.EMPLOYEE.APP.6 — Native Job Workspace

## Boundary

APP.6 establishes the first employee-facing Job Workspace as a read-only continuation of My Day. It consumes only `GET /api/v1/employee-operations/me/day`, whose server-side `User → Membership → Employee` resolution and assignment filtering remain authoritative. Knowing an Appointment or Job identifier does not grant access: every foreground, reconnect, and manual refresh rehydrates the own-day projection, and removed or reassigned work disappears.

The current Enterprise technician field-service APIs were inspected but are not composed in APP.6. Their lifecycle/evidence/commercial handoff boundary is owned by active TECH.FIELD work and is not needed to provide the employee-safe workspace. APP.6 therefore adds no Job, Dispatch, Scheduling, Customer, or Timekeeping mutation.

## Employee experience

An authorized employee opens the Job Workspace from an assignment in My Day. The workspace displays only projection-approved facts: scheduled window, Appointment and optional Job identity/status, assignment role/state, customer display name, service category, and bounded Service Location address. It contains no contacts, free-text notes, descriptions, customer history, financial facts, Payroll, or compensation.

The workspace labels cached detail as stale when offline or refresh fails. Authentication expiration, authorization denial, identity-not-ready, missing/reassigned assignment, offline, malformed response, and server failure remain distinct. Job state and My Time are explicitly independent.

The employee may deliberately hand the bounded address to the operating system's map application. This uses Apple Maps HTTPS links on iOS and a `geo:` intent on Android, adds no SDK, requests no location permission, reads no device location, and performs no background tracking or route optimization.

## Deferred authority

Acknowledgement, en route, arrival, start, pause, resume, notes/evidence, completion, commercial authorization, invoice handoff, and payment behavior are not part of APP.6. A later Mobile milestone must be explicitly approved to consume accepted technician execution contracts and must retain their assignment, permission, version, idempotency, and reconciliation rules.
