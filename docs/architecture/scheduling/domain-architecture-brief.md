# Scheduling Core Architecture

- **Program:** 2 — Operations
- **Domain:** 2.1 — Scheduling
- **Workstream:** 2.1.1 — Scheduling Core Architecture
- **Status:** Architecture review draft
- **Domain owner:** Scheduling within Operations

This Domain Architecture Brief follows the
[ACES DAB Standard](../../engineering/domain-architecture-brief-standard.md).
It defines governing boundaries and contracts; it does not claim that Scheduling
is implemented.

## 1. Purpose

Scheduling provides the authoritative record of when a Company has committed to
visit a Customer's Service Location. It must support reliable appointment
lifecycle management, Company and Branch calendars, capacity-aware time-window
selection, and controlled schedule changes without taking ownership of customer,
work execution, dispatch, sales, or financial facts.

The domain establishes a stable foundation for office schedulers, customer-service
staff, dispatchers, technicians, and future customer self-service channels.

## 2. Business Problem

Service businesses must coordinate customer availability, Branch operating rules,
work duration, and limited operational capacity. Informal calendars and mutable
time fields create double booking, ambiguous arrival promises, lost change history,
cross-Branch mistakes, and downstream disagreement about the current commitment.

ACP Enterprise needs one Company-scoped scheduling authority that makes time
semantics and lifecycle rules explicit while allowing Dispatch, Jobs, Customer
Management, Communications, and Analytics to use the same appointment identity.

## 3. Scope

Scheduling Core includes:

- creating and reading Appointments for an authorized Company and Branch;
- selecting, reserving, confirming, rescheduling, cancelling, and closing an
  Appointment through controlled lifecycle operations;
- customer-facing arrival windows and internal expected service duration;
- Branch scheduling calendars, operating intervals, closures, and exception days;
- availability evaluation using Branch capacity and externally supplied workforce
  availability;
- hard scheduling constraints, controlled override decisions, and conflict results;
- immutable change attribution and Business Event publication;
- Company, Branch, Customer, and Service Location reference validation;
- conceptual service and HTTP contracts for later implementation.

The first implementation should support single-occurrence Appointments. It must
preserve seams for later resources and optimization without adding speculative
records.

## 4. Out of Scope

Scheduling does not own or implement:

- Jobs, work orders, job execution, job costing, or completion evidence;
- Customer, Contact, or Service Location identity and maintenance;
- Estimates, pricebooks, estimate approval, or sales conversion;
- technician assignment, dispatch-board decisions, live technician state, or
  route execution;
- Invoices, Payments, refunds, tax, or accounting;
- employee identity, skills, shifts, time off, payroll, or human-resources policy;
- customer communications, reminders, consent, or delivery attempts;
- route optimization, recurring appointments, waitlists, online booking, or
  external-calendar synchronization;
- frontend calendar or dispatch-board design;
- implementation-level schemas, persistence models, migrations, or APIs.

An Appointment may reference an Estimate or Job in a future reviewed contract,
but that reference does not transfer ownership of either object to Scheduling.

## 5. Business Workflow

### Standard scheduling

1. An authenticated actor selects an active Company and an authorized active
   Branch.
2. The actor selects a Company-owned active Customer and active Service Location.
3. Scheduling evaluates the requested date range against the Branch calendar,
   existing capacity reservations, and available workforce signals.
4. Scheduling returns candidate time windows without reserving them. Availability
   is advisory until the create or reschedule transaction succeeds.
5. The actor submits an Appointment command with a selected window, expected
   duration, service intent, and idempotency key.
6. Scheduling revalidates all references and constraints inside the mutation
   boundary, reserves capacity, persists the Appointment, and stages its Business
   Event atomically.
7. Downstream modules consume committed events for communications, dispatch
   planning, analytics, and later work creation.

### Change and recovery paths

- Confirmation records customer acknowledgement without reserving capacity again.
- Rescheduling validates and reserves the replacement window before releasing the
  prior commitment in one transaction. A failed replacement leaves the original
  schedule unchanged.
- Cancellation requires a controlled reason, releases capacity, preserves history,
  and publishes a cancellation event. It never hard-deletes the Appointment.
- Constraint conflicts return a stable conflict result and make no partial change.
- A permitted override records its controlled reason and attribution; permission
  alone never silently suppresses a constraint.
- Duplicate retryable commands return the original result or a consistent conflict
  according to their idempotency contract.

## 6. Business Objects

### Appointment

The Appointment is the Scheduling aggregate root and durable source of truth for
the service-time commitment. Its conceptual data includes:

- stable Appointment identifier and Company and Branch ownership;
- Customer and Service Location identifiers;
- lifecycle status;
- arrival-window start and end instants;
- expected service duration;
- scheduling timezone retained for business interpretation;
- service summary and externally owned reference identifiers where approved;
- cancellation reason and change attribution where applicable;
- creation, update, confirmation, cancellation, and terminal timestamps;
- optimistic or equivalent concurrency version.

Appointment data must not duplicate mutable Customer profiles, Dispatch
assignments, Job state, estimate totals, invoice balances, or payment facts.
Historical contact or address snapshots, if later required for legal or operational
evidence, require a separately reviewed data-minimization design.

### Scheduling lifecycle

The initial lifecycle is:

```text
draft ──► scheduled ──► confirmed
  │            │             │
  └────────────┴─────────────┴──► cancelled
               │             │
               └─────────────┴──► completed | no_show
```

- `draft` is incomplete and does not reserve capacity.
- `scheduled` is a committed window and reserves capacity.
- `confirmed` is a scheduled commitment acknowledged by the Customer; it does not
  reserve additional capacity.
- `cancelled`, `completed`, and `no_show` are terminal.
- Rescheduling is an operation and historical fact, not a durable status. After a
  successful reschedule the Appointment remains `scheduled` or `confirmed` under
  an explicit confirmation-retention policy.
- Dispatch states such as assigned, en route, and arrived are not Appointment
  lifecycle states.

The exact transition matrix and confirmation-retention rule must be approved with
the implementation brief and enforced by one Scheduling service boundary.

### Time window model

- `window_start` is inclusive and `window_end` is exclusive: `[start, end)`.
- Both are stored and exchanged as offset-aware instants and normalized to UTC.
- `window_end` must be later than `window_start`.
- The arrival window is the customer promise; expected service duration is a
  separate capacity input and may extend beyond that arrival window.
- Branch business rules use the Branch's configured IANA timezone. A request must
  not choose an arbitrary timezone to evade calendar policy.
- Nonexistent daylight-saving local times are rejected. Ambiguous local times
  require an explicit offset or otherwise unambiguous instant.
- Calendar-day queries define boundaries in the Branch timezone and return the
  applicable timezone with results.

### Branch scheduling calendar

Scheduling owns rules that describe when a Branch may accept Appointments:

- regular weekly operating intervals;
- dated closures and exception intervals;
- booking horizon and minimum notice;
- permitted service-window increments;
- controlled over-capacity or after-hours override policy.

The Platform owns Branch identity, active/archive state, and configured timezone.
A calendar cannot make an inactive or archived Branch schedulable.

### Availability and capacity projections

Candidate windows, technician availability, and capacity summaries are computed
projections, not independent sources of truth.

- **Technician availability:** workforce or Dispatch-owned inputs describe shifts,
  time off, qualifications, and existing commitments. Scheduling may evaluate
  aggregate feasibility or capability requirements but does not assign a
  technician.
- **Branch availability:** combines the Branch calendar, active Appointment demand,
  expected duration, approved capacity policy, and current workforce signals.
- **Capacity:** represents a bounded operational promise for an interval. Capacity
  demand and supply units must be explicit and comparable; absence of data fails
  closed for hard-capacity booking unless a controlled override is authorized.
- Availability reads never guarantee a subsequent write. Creation and rescheduling
  must repeat decisive checks under concurrency control.

### Scheduling constraints

Hard constraints include:

- active Company, Membership, Branch authorization, Customer, and Service Location;
- Customer and Service Location ownership by the active Company;
- Service Location belonging to the selected Customer;
- valid UTC instants, positive duration, Branch timezone, and booking horizon;
- Branch calendar inclusion and absence of a closure;
- sufficient capacity and prevention of prohibited overlap;
- valid lifecycle transition and current concurrency version.

Soft constraints may rank windows for travel, preferred technician capability,
customer preference, or workload balance. Soft constraints must not be presented
as guaranteed assignments. Every hard-constraint override requires an explicit
permission, controlled reason code, attribution, and audit record.

### Rescheduling and cancellation

Rescheduling preserves the Appointment identifier and records old and new window
facts in a non-sensitive event. It is atomic with capacity movement and rejects a
stale version or unavailable replacement window.

Cancellation preserves the Appointment and its history. A controlled reason and
actor are required; optional notes must follow sensitive-data rules. Repeated
cancellation is idempotent only when it expresses the same terminal intent.
Downstream cancellation consequences belong to their owning domains and occur
through their APIs or consumed events, never cross-table writes.

## 7. Object Ownership

| Object or rule | Owner | Scheduling relationship |
| --- | --- | --- |
| Appointment and lifecycle | Scheduling | Authoritative aggregate and transition policy |
| Arrival window and expected duration | Scheduling | Authoritative scheduling commitment |
| Branch scheduling calendar | Scheduling | Owns bookable intervals and scheduling exceptions |
| Capacity reservation for Appointments | Scheduling | Mutated atomically with Appointment commands |
| Company and Branch identity/status | Platform | Referenced and validated; never mutated |
| User, Membership, Permission, Branch access | Platform Authorization | Supplied through `AuthorizationContext` |
| Customer and Contact | Customer domain | Referenced/read through stable contracts |
| Service Location | Customer domain | Required service-site reference; never mutated |
| Estimate | Sales | Optional future reference only |
| Job or work order | Jobs/Operations | Optional future reference; execution remains external |
| Technician identity, shift, time off, skills | Workforce/HR | Availability input only |
| Technician assignment and route decision | Dispatch | Consumes Appointment facts; never owned by Scheduling |
| Invoice and Payment | Financial | No Scheduling ownership |
| Reminder and delivery attempt | Communications | Triggered from events; delivery remains external |

The future `SchedulingService` owns business orchestration and transaction
boundaries. An Appointment repository owns Scheduling persistence and locking but
does not authorize, publish events, or write other modules' tables. Cross-domain
validation uses stable service/query interfaces or projections. Direct cross-module
persistence writes are prohibited.

## 8. Public APIs

The following `/api/v1` contracts are conceptual and require a later implementation
review:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/appointments` | Bounded Company/Branch-scoped collection |
| `POST` | `/api/v1/appointments` | Create and schedule an Appointment |
| `GET` | `/api/v1/appointments/{appointment_id}` | Retrieve an authorized Appointment |
| `PATCH` | `/api/v1/appointments/{appointment_id}` | Update non-lifecycle scheduling details |
| `POST` | `/api/v1/appointments/{appointment_id}/confirm` | Confirm the current commitment |
| `POST` | `/api/v1/appointments/{appointment_id}/reschedule` | Atomically replace the time commitment |
| `POST` | `/api/v1/appointments/{appointment_id}/cancel` | Cancel with a controlled reason |
| `POST` | `/api/v1/appointments/{appointment_id}/no-show` | Record the terminal no-show outcome |
| `GET` | `/api/v1/scheduling/availability` | Return bounded candidate windows |

Contracts must reject unknown fields, derive Company and actor from
`AuthorizationContext`, validate an explicit authorized Branch, conceal
cross-Company resources as not found, and use stable error envelopes. Creation and
retry-prone commands require idempotency. Collections require deterministic bounded
pagination and tenant filtering before user filters. Availability conflicts return
`409`; input validation returns `422`.

No public API may assign technicians, mutate Customers or Service Locations, or
create Jobs, Estimates, Invoices, or Payments.

## 9. Events Published

Scheduling stages Business Events through the existing `BusinessEventService` in
the same transaction as the Appointment change:

| Event | Trigger and payload purpose |
| --- | --- |
| `appointment.created` | Stable identifiers, Branch, initial lifecycle, and schedule reference |
| `appointment.scheduled` | First committed capacity-bearing time window |
| `appointment.confirmed` | Customer confirmation of the current commitment |
| `appointment.updated` | Approved non-lifecycle fields and changed-field names |
| `appointment.rescheduled` | Previous and replacement window instants and reason code |
| `appointment.cancelled` | Terminal cancellation timestamp and controlled reason code |
| `appointment.completed` | Scheduling record closed following an authoritative downstream outcome |
| `appointment.no_show_recorded` | Terminal no-show timestamp and controlled reason code |
| `scheduling.capacity_overridden` | Interval, override reason, actor, and affected Appointment |
| `scheduling.calendar_changed` | Branch calendar identity and effective change range |

Every event includes Company, applicable Branch, aggregate identifier, actor when
available, occurrence time, correlation/idempotency metadata, and schema version.
Payloads exclude gate codes, notes, contact details, credentials, and unrestricted
free text. Security-sensitive override and administration actions additionally
produce Security or Enterprise Audit records through their existing owners; those
records do not replace Business Events.

## 10. Events Consumed

Initial synchronous command validation uses authoritative Customer and Platform
interfaces. Event consumers are introduced only when their producer contracts and
recovery behavior are approved. Planned consumption boundaries are:

| Producer event | Scheduling behavior |
| --- | --- |
| Customer status/archive change | Prevent new commitments when ineligible and flag affected future Appointments; never auto-cancel without explicit policy |
| Service Location deactivation | Prevent new commitments and flag future Appointments for review |
| Branch status/archive change | Prevent new commitments; preserve existing Appointment history |
| Workforce availability change | Refresh availability projections without assigning technicians |
| Job completion or no-show outcome | Close the linked Appointment only through an idempotent, explicitly mapped transition |

Exact event names are governed by each producing domain and must be reconciled at
implementation review. Consumers store or derive an event idempotency key, tolerate
duplicate delivery, reject invalid Company relationships, and do not assume global
ordering. Failures retry through the established event-processing mechanism and do
not make the producer's committed transaction disappear. Null-Company events never
affect Company scheduling data.

## 11. Security Model

- Every API requires Authentication and a resolved `AuthorizationContext` before
  Scheduling executes.
- Proposed centralized permissions are `company.appointment.read`,
  `company.appointment.manage`, `company.appointment.cancel`,
  `company.scheduling.calendar.manage`, and
  `company.scheduling.capacity.override`. Exact catalog registration is reviewed
  with implementation; no role name implies access.
- Appointment operations require both active Company Membership and authorization
  for the Appointment's active Branch. Permission does not expand Branch access.
- Company, Branch, actor, and authorization versions are server-derived. Request
  bodies cannot select an unauthorized tenant or Branch.
- Repository queries scope by Company before applying resource identifiers or
  filters. Unknown and cross-Company resources receive the same concealed response.
- Inactive Users, Memberships, Companies, Branches, Customers, and Service
  Locations fail closed according to their owner contracts.
- Schedule notes and customer-facing context are minimized and excluded from logs,
  event payloads, metrics labels, and generic errors.
- Capacity overrides, calendar administration, rescheduling, and cancellation are
  attributable and auditable. Authorization denials retain controlled internal
  reasons while clients receive safe responses.
- Rate limits and idempotency controls protect availability searches and mutation
  retries without weakening transactional checks.

## 12. Dependencies

Scheduling depends on approved contracts, not another module's tables:

```text
Authenticated client
        │
        ▼
Scheduling API ──► Platform Authentication and AuthorizationContext
        │
        ▼
SchedulingService ──► AppointmentRepository ──► PostgreSQL
        │                         │
        │                         └── Appointment + calendar + capacity state
        ├──► Customer domain ─────── Customer + Service Location validation
        ├──► Platform ────────────── Company + Branch identity/status/timezone
        ├──► Workforce projection ── availability/capability input
        └──► BusinessEventService ── committed Scheduling events

Scheduling events ──► Dispatch / Communications / Analytics / Automation
Dispatch decisions ─► assignments and routes (not Scheduling persistence)
Future Job links ───► Jobs/Operations contract (not Scheduling ownership)
```

Existing dependencies are Foundation time/UUID/database conventions, the Business
Event Engine, Platform Authentication and Authorization, Enterprise Audit, Customer
and Service Location contracts, and Company/Branch reference data. Dispatch,
Workforce, Communications, Jobs, and optimization contracts remain downstream or
future dependencies and must not block the core ownership model.

## 13. Risks

| Risk | Control or required decision |
| --- | --- |
| Overbooking under concurrent writes | Recheck constraints in the mutation transaction; use PostgreSQL locking/constraints and deterministic ordering |
| DST or timezone ambiguity | Store UTC instants, retain Branch IANA timezone, reject nonexistent/ambiguous local inputs |
| Cross-Company or cross-Branch disclosure | Resolve centralized context and scope every repository query before resource filters |
| Stale availability projection | Treat reads as advisory and revalidate on commit |
| Ownership creep into Dispatch or Jobs | Enforce the ownership table and communicate through contracts/events |
| Customer or location deactivated after booking | Preserve history, block new use, and create a review path rather than silently cancelling |
| Cancellation creates inconsistent downstream state | Publish one committed event; require idempotent downstream handling and visible exceptions |
| Sensitive location/contact data leaks through events | Publish identifiers and controlled metadata only |
| Capacity model is too coarse or premature | Begin with explicit, measurable units and version the policy without changing Appointment ownership |
| Route optimization mutates commitments unexpectedly | Optimization returns proposals; Scheduling alone applies authorized changes |
| Calendar query growth | Bound date ranges, index by Company/Branch/time, and test query plans during persistence design |

## 14. Acceptance Criteria

This architecture is ready for implementation review when:

1. Appointment, lifecycle, time-window, calendar, and capacity ownership are
   unambiguous.
2. Jobs, Customers, Estimates, Dispatch assignments, Invoices, and Payments remain
   outside Scheduling ownership.
3. Lifecycle transitions, rescheduling, cancellation, and history preservation are
   defined without hard deletion.
4. UTC, Branch timezone, interval, duration, and daylight-saving semantics are
   explicit.
5. Company and Branch isolation, centralized permissions, missing-resource
   concealment, and controlled overrides fail closed.
6. Candidate availability is advisory and concurrent booking has a database-backed
   revalidation strategy.
7. Customer and Service Location relationships use authoritative external
   identities without cross-module writes.
8. Conceptual APIs are bounded, idempotent where required, and do not expose
   adjacent-domain mutations.
9. Published events are transactional, versioned, non-sensitive, and attributable.
10. Consumed-event behavior addresses idempotency, tenant validation, retries, and
    lack of global ordering.
11. Dispatch and future route optimization can consume or propose changes without
    becoming Appointment owners.
12. A later implementation DAB revision specifies the approved state matrix,
    capacity units, persistence constraints, query plans, API schemas, and test
    cases before code begins.

## 15. Future Extension Points

The architecture preserves reviewed seams for:

- route-optimization proposals and travel-time buffers;
- recurring and multi-visit appointment series;
- customer self-scheduling, waitlists, and expiring reservation holds;
- multi-technician crews, equipment, rooms, and other schedulable resources;
- capability-aware matching and predictive duration recommendations;
- external calendar synchronization;
- automated reminders through Communications;
- linked Estimate and Job workflows through stable identifiers and events;
- calendar and capacity projections for Analytics and Mission Control;
- AI-assisted recommendations that remain explainable proposals and require the
  same authorization and mutation service as human actions.

None of these extensions may bypass Scheduling lifecycle rules, silently assign
Dispatch resources, or mutate an Appointment outside the Scheduling service.
