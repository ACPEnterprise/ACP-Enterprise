# BANK.BEA.002 — Evidence-bound signal evaluation

## Boundary

The evidence-evaluation registry is the single Beacon-owned map from each
immutable BANK.BEA.001 definition to its required fact contract, provider-neutral
adapter, deterministic evaluator, readiness classification, limitations, and
blocking evidence. Operational domains continue to own facts. Beacon neither
mutates those domains nor reads Migration or QBO evidence.

`EVALUABLE` requires a complete accepted adapter and evaluator with no blocker.
`PARTIALLY_EVALUABLE` preserves named facts that exist alongside the exact missing
policy, identity, effective-time, or conflict evidence. `NOT_EVALUABLE` means the
authoritative fact domain does not exist. `CONFLICTING` is available as a
fail-closed runtime classification when accepted authority contradicts itself;
the current repository-level capability review found no definition whose source
contracts themselves conflict.

## Current readiness matrix

| Definition | State | Source contract | Evaluator | Blocker |
| --- | --- | --- | --- | --- |
| `operational.scheduling.appointment_unassigned` | PARTIALLY_EVALUABLE | Appointment + DispatchAssignment | No | Missing accepted as-of unassigned reconciliation contract |
| `operational.scheduling.appointment_overdue` | EVALUABLE | Beacon overdue Appointment snapshot | Yes | — |
| `operational.scheduling.scheduled_start_missed` | PARTIALLY_EVALUABLE | Appointment + arrival evidence | No | Missing start tolerance and accepted start-event contract |
| `operational.scheduling.authoritative_conflict` | PARTIALLY_EVALUABLE | Scheduling overlap query | No | No durable accepted conflict evidence identity |
| `operational.dispatch.job_awaiting_dispatch` | PARTIALLY_EVALUABLE | Job + explicit Appointment link + assignment | No | Missing dispatch-eligibility contract |
| `operational.dispatch.assigned_resource_unavailable` | PARTIALLY_EVALUABLE | Assignment + WorkforceAvailability | No | Missing effective-time reconciliation |
| `operational.dispatch.state_stalled` | PARTIALLY_EVALUABLE | Assignment history | No | Missing state-duration policy |
| `operational.dispatch.arrival_execution_mismatch` | PARTIALLY_EVALUABLE | Arrival + Job execution evidence | No | Missing accepted cross-domain reconciliation identity |
| `operational.job.intermediate_state_stalled` | EVALUABLE | Beacon paused Job snapshot | Yes | — |
| `operational.job.completion_evidence_inconsistent` | PARTIALLY_EVALUABLE | Completion guards + field evidence | No | Missing contradiction fact contract |
| `operational.job.lifecycle_inconsistent` | PARTIALLY_EVALUABLE | Job transition history | No | Missing historical inconsistency evidence contract |
| `operational.job.follow_up_incomplete` | NOT_EVALUABLE | No required-follow-up authority | No | No authoritative requirement/lifecycle |
| `operational.location.required_data_missing` | PARTIALLY_EVALUABLE | ServiceLocation | No | Missing operational required-field policy |
| `operational.location.contact_condition_unresolved` | NOT_EVALUABLE | No contact-condition authority | No | No authoritative condition lifecycle |
| `operational.location.service_restriction_active` | NOT_EVALUABLE | No Customer restriction authority | No | Workforce restrictions are not Customer policy |
| `operational.estimate.approved_workflow_not_advanced` | PARTIALLY_EVALUABLE | Approval + explicit EstimateConversionRecord | No | Missing duration and target-state policy |
| `operational.invoice.workflow_stalled` | PARTIALLY_EVALUABLE | Invoice lifecycle | No | Missing operational stall duration policy |
| `operational.payment.evidence_inconsistent` | PARTIALLY_EVALUABLE | Payment lifecycle/evidence | No | Missing operational contradiction contract |
| `operational.workforce.assignment_ineligible` | PARTIALLY_EVALUABLE | Assignment + capability/availability | No | Missing immutable assignment-time eligibility evidence |
| `operational.workforce.capability_requirement_missing` | PARTIALLY_EVALUABLE | Capability profiles + dispatch requirements | No | Job lacks accepted immutable capability requirement identity |
| `operational.workforce.staffing_availability_mismatch` | PARTIALLY_EVALUABLE | Assignment + WorkforceAvailability | No | Missing replayable assignment-time reconciliation evidence |

## Evaluation and lifecycle

The two admitted definitions continue through the existing
`SqlBeaconFactRepository`, immutable snapshot, deterministic definition-bound
evaluation, priority, UUIDv5 identity, expiration, and lifecycle projection. The
registry verifies every emitted existing evaluator rule has catalog authority;
the legacy past-due-invoice rule remains backward compatible but is not admitted
as a BANK.BEA.002 operational evaluator because its accepted implementation
contains financial exposure ranking outside this milestone.

Unchanged facts produce the same condition, evidence digest, signal identity,
severity, priority, and explanation. Empty/cleared facts produce no current
signal. Existing acknowledgement, review, snooze, suppression, and expiration
remain untouched.

`GET /api/v1/beacon/evaluation-readiness` exposes safe Company/active-Branch
readiness metadata. It does not return raw facts, reserve work, notify anyone, or
perform a source-domain action.

## Successor

The exact successor is `BANK.BEA.003 — Signal confidence and freshness semantics`.
It must not activate a partially evaluable definition until its named blocker is
closed by authoritative evidence and separate scope approval.
