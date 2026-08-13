<!-- markdownlint-disable MD013 -->

# Technician Day-1 Field Execution Contract

## Authority and dependency

`TECH.FIELD.CONTRACT.1` freezes the minimum field journey required to stop normal technician work in Housecall Pro. It is an architecture/control contract only: it changes no runtime, schema, deployment, or environment.

`TECH.FIELD.1` is a successor to `TECH.1`, not a replacement for it. Its hard start dependency is an owner-accepted, integrated `TECH.1` implementation conforming to boundary version 2 and fingerprint `04980ac90a5d1ed0e379600ab7e02cdc4f74fc767572c10cd35a79e3280442c9`. At this contract's starting SHA, the durable scheduler still records `TECH.1` as `ready`; therefore `TECH.FIELD.1` is **PLANNED / dependency-blocked** and no implementation worktree may be created yet. This contract does not modify or adopt OM1's active TECH.1 worktree.

The authoritative implementation boundary is [tech-field-1-execution-boundary.json](tech-field-1-execution-boundary.json). The existing [TECH.1 boundary](tech-1-execution-boundary.md) continues to govern the shell.

## Day-1 authority model

Existing domain owners remain authoritative:

- Identity, Employee, Workforce capability, Company, Branch, and permission services own the actor identity and access scope. A role label or job title never proves technician eligibility.
- Scheduling owns the appointment and itinerary window; Dispatch owns assignment, acknowledgement, `en_route`, `arrived`, exception, and reconciliation-required state.
- Jobs owns `ready`, `in_progress`, `paused`, and `completed` transitions and their optimistic concurrency version.
- Customer and Service Location own customer/contact/address facts. The field projection exposes only the minimum facts required for assigned work.
- Price Book owns active catalog data. Estimates owns revisions, options, tax calculation inputs, presentation, acceptance, and approval evidence.
- Invoicing owns invoice creation, issue, adjustment, and AR facts. Payments owns external-processor results, applications, refunds, failures, deposits, clearing, and settlement facts once `PAY.1-3.ACCEL` is authoritative.
- `TECH.FIELD.1` owns the technician journey projection, assignment-aware command boundary, append-only field notes, completion requirements/evidence, customer work-approval evidence, and durable invoice/payment handoff status. It must call established domain services rather than duplicate those aggregates.

## Minimum field journey

### Authentication and itinerary

An active authenticated user must resolve to an active Employee with an eligible technician capability in the same Company and Branch as the assignment. The default itinerary contains only that technician's assigned appointments for the requested local service day, ordered deterministically by scheduled time and identifier. Supervisor/dispatcher access is a distinct permission and never inferred from technician access.

Each itinerary item exposes appointment and dispatch state, customer display/contact facts needed for service, Service Location address/access facts, Job identity/status/version, estimate readiness, and exception/handoff status. Cross-Company and unauthorized cross-Branch records are concealed.

### Dispatch and work state

The Day-1 command sequence is:

1. acknowledge the authoritative active assignment when required;
2. record `en_route` (on my way) and `arrived` through Dispatch;
3. start the linked ready Job after arrival;
4. pause with a controlled reason and resume using the current Job version;
5. record required notes and evidence during work;
6. satisfy completion requirements and complete the Job;
7. create or retry the invoice handoff from the exact accepted Estimate and completed Job;
8. expose the resulting invoice/payment handoff without inventing financial state.

Start requires the acting technician's current active assignment to the linked appointment, acknowledged assignment state, and `arrived` evidence. An authorized supervisor may use a separately audited override with a controlled reason. Dispatch reconciliation-required or exception state fails closed.

All mutations require a client-generated idempotency key, current aggregate version where the owner supports optimistic concurrency, actor identity, Company, Branch, Job, appointment/assignment identity, and observed timestamp. Exact replay returns the original result; a changed payload under the same key conflicts. Concurrent/stale commands fail with a refetchable conflict and never fabricate success.

### Notes, evidence, approval, and completion

The universal Day-1 completion set is:

- an append-only work-performed summary;
- a controlled completion disposition;
- actor, assignment, Job, Company/Branch, timestamps, and source command evidence;
- customer work-approval evidence, or a controlled `unavailable`/`refused` disposition with reason and supervisor-visible exception;
- every additional evidence item explicitly required by the Job's versioned completion-requirement snapshot.

Photos, forms, signatures, measurements, or other artifacts are required only when that immutable requirement snapshot says so. The implementation must not silently make an unconfigured artifact universally mandatory or treat missing evidence as false/zero. Amendments append correction/supersession evidence; they do not overwrite posted history.

The global Jobs completion path must invoke the field completion guard for field-assigned Jobs. A technician-specific route alone is insufficient because the generic Job completion endpoint would otherwise bypass evidence. The guard checks assignment, arrival, required evidence, customer disposition, accepted Estimate or explicitly authorized non-billable disposition, and unresolved reconciliation state before Jobs owns the atomic status transition. Existing Job Business Events remain the lifecycle authority.

After Job completion, a durable idempotent handoff requests invoice creation from the accepted Estimate. The handoff is `pending`, `completed`, or `reconciliation_required`; failures remain visible and retryable. A billable field closeout is not operationally closed until an invoice exists or an authorized non-billable disposition is recorded. Technicians cannot adjust, void, write off, or mark invoices paid through this boundary.

### Price Book, Estimate, invoice, and payment seams

The field experience may read active Price Book entries and compose the accepted Estimate APIs; it must not copy pricing or tax logic. Work approval is distinct from Estimate acceptance, and both retain their own evidence.

Invoice handoff uses authoritative Invoicing APIs/events. Payment handoff is fail-closed until `PAY.1-3.ACCEL` is accepted and integrated. Once present, the field experience may initiate the approved external-processor flow and display authoritative status. It never stores raw card data, fabricates receipt/settlement, or marks an invoice paid. An office-completed payment remains compatible with Day 1, but end-to-end cutover acceptance requires the accepted Payment path.

### Failure and degraded network behavior

Day 1 does not promise offline-first mutation. The client may show a timestamped, encrypted-platform-protected cached read projection, but must label it stale and retain no unnecessary customer data. A command without durable server acknowledgement remains `not sent` or `pending confirmation`, not complete. Reconnect retries the same idempotency key, refreshes authoritative state, and resolves conflicts explicitly. No local-only lifecycle, approval, completion, invoice, or payment fact is authoritative.

## Audit and Business Events

Every accepted command records the authenticated actor, Employee/technician identity, Company, Branch, assignment, appointment, Job, idempotency key, aggregate version, timestamp, and correlation/causation identifiers. Append-only field evidence and audit records survive correction.

Existing Dispatch and Job events remain authoritative. `TECH.FIELD.1` adds versioned events for field note/evidence recording, customer work-approval disposition, completion-requirement satisfaction, and invoice-handoff requested/completed/reconciliation-required. `ACC.POST.1` may consume authoritative Invoice and Payment events; technician events never post journals directly.

## Permissions and isolation

The packet may add the closed permissions `COMPANY_TECHNICIAN_READ` and `COMPANY_TECHNICIAN_EXECUTE` to the central catalog if the accepted TECH.1 implementation has not already supplied equivalent codes. Read grants assigned-itinerary and minimum-context access. Execute grants assignment acknowledgement and the field command path, subject to assignment ownership. Supervisor override requires the existing domain manage permission or one explicit audited permission selected during implementation; it cannot be implied by technician execute.

Every repository query and mutation is scoped by Company and Branch. Assignment ownership, Employee active state, Workforce eligibility, and permission are checked server-side. Tests must prove same-Company cross-Branch and cross-Company denial/concealment, inactive identity denial, unassigned technician denial, and privileged override audit.

## Day-1 versus post-cutover

Day 1 includes the authenticated assigned itinerary; minimum customer/location/Job context; acknowledgement/en-route/arrival; start/pause/resume/complete; append-only notes; policy-required evidence; customer approval disposition; Price Book/Estimate composition; invoice/payment handoffs; reconnect-safe idempotency; permissions/isolation; audit/events; and physical mobile acceptance.

Post-cutover enhancements include route optimization, background GPS/live map tracking, offline-first mutation queues, generalized form builder, universal media markup, messaging polish, performance analytics, advanced time tracking, broad tablet/device optimization, and competitive feature parity. They cannot enter the `TECH.FIELD.1` boundary unless separately approved.

## Acceptance criteria

Acceptance requires all of the following:

- physical iPhone Safari proves the complete assigned appointment journey from itinerary through completed Job and authoritative invoice handoff;
- a representative external-processor payment handoff is proven after the Payment dependency is accepted, without exposing payment credentials or raw card data;
- required evidence and customer disposition block completion when absent and pass when satisfied;
- generic and technician Job completion paths both enforce the same field guard;
- duplicate, stale, reordered, refresh, reconnect, and retry commands preserve one outcome and truthful UI;
- unauthorized Employee, unassigned technician, cross-Branch, cross-Company, and inactive identity cases fail closed;
- Dispatch exception/reconciliation-required state blocks unsafe work transitions;
- audit and Business Events correlate assignment, Job, evidence, invoice handoff, actor, and command;
- backend/frontend focused suites, affected Jobs/Dispatch/Estimate/Invoicing regressions, authorization tests, lint/type/build, migration lifecycle, drift, and exactly-one-head validation pass;
- Preview closed-loop rehearsal passes under separate deployment authority, followed by separate owner acceptance. Production and cutover remain separately gated.
