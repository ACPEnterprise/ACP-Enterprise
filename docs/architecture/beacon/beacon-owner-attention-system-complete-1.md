# Beacon owner attention system complete 1

## Authority boundary

Beacon notices deterministic, evidence-backed conditions and records only Beacon review/ownership workflow. It does not mutate Customers, Jobs, Scheduling, Dispatch, Workforce, Payroll, Accounting, Payments, Economics, Price Book, Inventory, or Communications.

Luminary owns economic interpretation. LIA may present Beacon's permission-bounded intelligence packet and recommended human action, but cannot use it as source-domain mutation authority.

## Authoritative foundation

Current protected authority already provides:

- stable definition/version and catalog digests;
- Company and optional Branch scope;
- evidence-bound stable signal and root-condition identities;
- deterministic severity and priority with visible factors;
- evidence completeness, freshness, reconciliation, confidence, and limitations;
- expiration and stale-command rejection;
- acknowledgement, review, snooze, ownership, assignment, transfer, and history;
- explicit evaluation and escalation readiness registries;
- a permission-scoped Beacon intelligence packet for LIA;
- safe source drillback without autonomous action.

The operational catalog contains 21 definitions across Scheduling, Dispatch, Job lifecycle, Customer/Location, Estimate workflow, Invoice/Payment workflow, and Workforce/Technician. The financial/control catalog contains 12 provider-neutral native Invoice, Payment, AP, Accounting, and report-control definitions.

## Active versus readiness-only signal families

Actively composed by the current live snapshot evaluator:

- overdue committed Appointments;
- paused Jobs;
- legacy past-due issued Invoices.

The native financial evaluator deterministically supports 12 definition-bound native fact types, but current owner queue orchestration does not yet load all of those source aggregates. They must not be described as active owner cards until a tenant/Branch-scoped adapter admits them into the queue.

The operational readiness registry truthfully marks 2 of 21 definitions evaluable, 16 partially evaluable, and 3 not evaluable. The system-readiness API publishes the exact blockers rather than manufacturing source facts or selecting missing business policy.

## Owner attention windows

The owner dashboard now groups admitted current signals deterministically:

- **NOW** — critical severity or critical/immediate priority;
- **TODAY** — important severity or priority;
- **THIS WEEK** — attention severity without stronger urgency evidence;
- **WATCH** — informational/monitor conditions.

The grouping never changes source-domain state and does not imply a response deadline beyond evidence encoded in severity and priority.

## Morning brief

`GET /api/v1/beacon/morning-brief` returns a Company/Branch-scoped deterministic digest, current attention windows, unresolved count, acknowledged count, snoozed count, and urgent-today count.

Beacon does not persist periodic evaluation snapshots today. Therefore `new_since_yesterday` and `resolved_since_yesterday` are explicitly unavailable rather than inferred from request-time evaluation. Persisted append-only evaluation history is the exact dependency for those two deltas.

Delivery readiness is explicit:

- owner dashboard: ready;
- Mobile inbox: not yet composed;
- external email/push: not ready and no provider is invoked.

## Dedupe and lifecycle

Signals share a stable root-condition key across evidence successors. Exact replay preserves identity. Changed evidence creates a new signal identity while lifecycle events apply only when their evidence digest matches. Snoozed signals remain unresolved, are excluded from the active queue, and return after snooze expiry or evidence change. Disappearing evidence is not recorded as resolved because no append-only evaluation history currently proves that transition.

## Unsupported or authority-gated families

The following requested families remain source or policy gated and must not emit inferred signals:

- source acquisition, Migration hold, and binding/history completeness beyond accepted Data Quality evidence;
- missing Appointment/assignment and double-booking without accepted as-of/conflict evidence;
- timecard/Payroll blockers without a bounded Beacon adapter over authoritative blocker records;
- Accounting report/reconciliation conditions not yet composed into the owner queue;
- Economics findings without immutable Economics finding/result references;
- Price Book cost/activation review without accepted review and threshold policy;
- Inventory shortage/procurement delay without accepted requirement and effective-time evidence;
- capacity/workload imbalance without accepted capacity and significance policy;
- historical new/resolved morning deltas without persisted evaluation snapshots;
- Mobile/email/push delivery without Notification/Communications composition and preference policy.

These are readiness gaps, not zero conditions.

## Product acceptance

Verify an authorized owner can:

1. open Command Center and see NOW/TODAY/THIS WEEK/WATCH groups;
2. understand why each signal exists and which evidence supports it;
3. drill into permitted Job, Appointment, or Invoice evidence;
4. distinguish severity from deterministic priority;
5. review, acknowledge, snooze, claim, assign, transfer, and release responsibility where permitted;
6. observe stale/conflicting evidence limitations;
7. confirm snoozing does not resolve the source condition;
8. read the morning brief and see historical deltas reported unavailable;
9. retrieve a LIA-ready intelligence packet without receiving mutation authority;
10. confirm no external notification is sent.

Production policy remains unconfigured. No Production operation or operational-domain mutation is part of this capability.
