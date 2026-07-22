# Jobs Domain Architecture Brief

- **Program:** 2 — Operations
- **Domain:** Jobs and Work Execution
- **Milestone:** 8.1 — Jobs Architecture and Domain Contract
- **Status:** Approved for persistence implementation

## Purpose and business problem

Jobs is the authoritative bounded context for executing customer work. It gives
office and field operations one durable identity and controlled lifecycle for the
work to be performed without duplicating Customer, Scheduling, Dispatch, or
financial ownership.

The canonical backend and aggregate term is **Job**. Python uses `Job`, persistence
uses `jobs`, future APIs use `/api/v1/jobs`, events use `job.*`, the default UI label
is **Jobs**, and human-readable numbers use `JOB-000001`. “Work Order” may later be
a configurable display or printable synonym; it is not another aggregate.

## Scope

Jobs initially owns Job identity and numbering, Company and Branch scope, Customer
and Service Location references, controlled type and priority, work intent,
execution lifecycle, concurrency, terminal attribution, and links to scheduled
visits.

Jobs does not own Customers, Service Locations, Appointments, calendar capacity,
technician identity or assignment, Dispatch state, routes, time tracking, labor,
materials, inventory, equipment, estimates, invoices, payments, attachments,
photos, forms, checklists, signatures, warranties, communications delivery, GPS,
or ACP-EIQ behavior.

## Business workflow

1. A future authorized command validates Company, Branch, Customer, and Service
   Location references.
2. A Job is created with a UUID and Company-scoped number, initially as `draft`.
3. Zero or more Appointments may be explicitly linked as visits without mutating
   Scheduling.
4. A future Job service activates and executes the Job through controlled lifecycle
   transitions.
5. Mutations stage Company-scoped `job.*` Business Events in the same transaction.
6. Dispatch, financial, inventory, communications, and intelligence modules consume
   stable identifiers and events through their own boundaries.

## Aggregate and object ownership

The Job aggregate owns its identity, number, lifecycle, priority, type code,
customer-reported problem, internal description, concurrency version, operational
timestamps, terminal reason codes, and actor attribution. It stores references—not
mutable copies—of Company, Branch, Customer, Service Location, and Appointment.

Generic notes, technician notes, financial state, Scheduling windows, assignments,
materials, evidence, and forms are excluded. These require separately reviewed
ownership and access rules.

## Appointment relationship

The association is structurally many-to-many:

```text
Job 1 ── 0..* JobAppointmentLink
Appointment 1 ── 0..* JobAppointmentLink
```

An Appointment or Job may exist independently. A Job can link multiple visits. The
future Job service will normally enforce one Job per Appointment, but the database
does not impose a unique `appointment_id`; a separately approved workflow may later
permit reuse. Links are unique by `(job_id, appointment_id)` and by
`(job_id, visit_sequence)`.

Scheduling remains authoritative for Appointment timing, lifecycle, calendar, and
capacity. Jobs owns only the association record and cannot mutate Scheduling.
Appointment cancellation/rescheduling and Job completion/cancellation remain
independent domain operations. Conversion from Appointment to Job is explicit, not
automatic. Multi-visit work links more Appointments to the same Job; recurring work
and projects require later reviewed orchestration.

## Lifecycle

The future lifecycle is:

```text
draft → ready → in_progress ⇄ paused → completed
  └─────────────── controlled cancellation ─────→ cancelled
completed | cancelled ── reopen operation ──→ ready
```

Allowed persisted states are `draft`, `ready`, `in_progress`, `paused`, `completed`,
and `cancelled`. Dispatch states are excluded. Reopen is an operation, not a status;
no reopen snapshot fields or lifecycle-history table are persisted initially.
Durable future `job.reopened` events retain reopening facts.

`status` is the authoritative current lifecycle state. Completion and cancellation
groups preserve the most recent corresponding terminal occurrence and may remain
populated after reopening; historical terminal fields do not imply a current
terminal status. A reopened `ready` Job may retain `started_at`. Pause fields describe
only the active pause and are cleared on resume. Full lifecycle history remains a
future Business Event or projection concern.

Future services own transition rules, idempotency, row locking, and
optimistic-version checks; models and repositories contain no lifecycle
orchestration.

## Type and priority

`job_type_code` is a nullable, normalized lowercase code up to 64 characters. The
database validates shape, not a permanent business enum, preserving future
Company-configurable types without introducing an administration table now.

Priority is canonical and orders from least to most urgent:

1. `low`
2. `normal`
3. `high`
4. `urgent`
5. `emergency`

Priority does not grant Dispatch or override authority.

## Security and authorization

All records are Company-scoped and Branch-scoped where applicable. Future services
consume immutable `AuthorizationContext`; repositories apply Company predicates in
SQL and conceal cross-tenant resources. No post-query filtering is an isolation
boundary. Jobs cannot move between Branches in the initial contract.

Future permissions are expected to separate read, management, execution, and
override authority. Dispatch and assignment permissions remain separate. Permission
catalog additions use explicit synchronization for existing installations and never
mutate Roles at startup.

## Public contracts and events

Future commands and APIs are outside the persistence milestone. Transport-independent
commands will cover create, update, activate, start, pause, resume, complete, cancel,
and reopen operations. A future immutable `JobQuery` will follow the Scheduling Query
Engine pattern.

Expected Jobs-owned events include `job.created`, `job.updated`, `job.activated`,
`job.started`, `job.paused`, `job.resumed`, `job.completed`, `job.cancelled`,
`job.reopened`, and `job.appointment_linked`. Dispatch and assignment events remain
outside Jobs. Payloads contain stable identifiers and controlled values, not contact
details, notes, credentials, financial details, or mutable snapshots.

## Dependencies and extension points

Jobs depends on Platform identity and authorization, Customer references, Scheduling
Appointment references, PostgreSQL, and the Business Event Engine. Stable APIs,
immutable DTOs, identifiers, and events form seams for Dispatch, technician
assignment, time tracking, labor, inventory, estimates, invoices, payments,
attachments, forms, warranties, route optimization, GPS, reporting, and ACP-EIQ.
No module may write another module's tables.

## Risks and acceptance criteria

Expensive-to-reverse decisions include structurally reusable Appointment links,
prohibiting Branch transfer, avoiding generic notes, allocating Job numbers at draft
creation, and deferring lifecycle history. The future one-Job-per-Appointment policy
must be enforced under locking by the Job service, not assumed from persistence.

The persistence foundation is acceptable when numbering is atomic and Company
scoped; cross-domain references remain consistent; links are structurally
many-to-many; lifecycle metadata is constrained; repository reads and locks conceal
cross-Company records; migration downgrade removes all Jobs-owned objects; and no
service, API, frontend, Dispatch, or financial behavior is introduced.
