# BANK.BEA.003 — Signal confidence and freshness semantics

## Deterministic quality boundary

Beacon quality describes an already admissible operational conclusion; it never
creates admission. The BANK.BEA.002 readiness registry remains authoritative.
PARTIALLY_EVALUABLE, NOT_EVALUABLE, and CONFLICTING definitions cannot become
evaluable through a LOW, MODERATE, or any other confidence label.

Confidence is semantic, not numeric: HIGH, MODERATE, LOW, UNKNOWN, and
CONFLICTING. It derives only from completeness, reconciliation, accepted
limitations, conflicts, and freshness. No probability, model score, AI judgment,
or subjective weighting exists.

Freshness is CURRENT, STALE, or UNKNOWN. It requires an evidence as-of timestamp,
evaluation timestamp, and a definition-bound policy. Missing timestamps or policy
produce UNKNOWN. Future as-of timestamps also produce UNKNOWN rather than an
invented clock correction.

## Quality envelope

The immutable reconstructed envelope contains definition identity/version, source
authority, evidence identities, effective and as-of timestamps, evaluation time,
completeness, reconciliation, freshness, confidence, policy identity/version,
stale behavior, limitations, conflict identities, evidence digest, deterministic
quality digest, admissibility, and an explanation-safe summary. Raw evidence
identities remain outside public signal projections.

Quality metadata does not participate in the existing signal UUID or condition
evidence digest. Semantically identical evidence therefore retains its existing
identity and lifecycle history. The separate quality digest changes when accepted
quality inputs change.

## Accepted freshness policies

The two EVALUABLE definitions use their accepted BANK.BEA.001 definition-v1
`ttl_seconds=900` as snapshot-recency policy version 1. Evidence observed no more
than 900 seconds before evaluation is CURRENT. Older evidence is STALE and the
declared behavior is BLOCK_EVALUATION. No AGING threshold is introduced because
no accepted intermediate threshold exists.

All nineteen blocked definitions have confidence semantics but no approved
freshness policy. Their freshness remains UNKNOWN and their BANK.BEA.002 blocker
remains controlling.

| Definition | Readiness | Confidence | Freshness | Policy source/version | Remaining blocker |
| --- | --- | --- | --- | --- | --- |
| `operational.scheduling.appointment_unassigned` | PARTIALLY_EVALUABLE | Yes | No | None | Missing accepted as-of unassigned reconciliation contract |
| `operational.scheduling.appointment_overdue` | EVALUABLE | Yes | Yes | Definition v1 TTL / policy v1 | — |
| `operational.scheduling.scheduled_start_missed` | PARTIALLY_EVALUABLE | Yes | No | None | Missing start tolerance and accepted start-event contract |
| `operational.scheduling.authoritative_conflict` | PARTIALLY_EVALUABLE | Yes | No | None | No durable accepted conflict identity |
| `operational.dispatch.job_awaiting_dispatch` | PARTIALLY_EVALUABLE | Yes | No | None | Missing dispatch-eligibility contract |
| `operational.dispatch.assigned_resource_unavailable` | PARTIALLY_EVALUABLE | Yes | No | None | Missing effective-time reconciliation |
| `operational.dispatch.state_stalled` | PARTIALLY_EVALUABLE | Yes | No | None | Missing per-state duration policy |
| `operational.dispatch.arrival_execution_mismatch` | PARTIALLY_EVALUABLE | Yes | No | None | Missing cross-domain reconciliation identity |
| `operational.job.intermediate_state_stalled` | EVALUABLE | Yes | Yes | Definition v1 TTL / policy v1 | — |
| `operational.job.completion_evidence_inconsistent` | PARTIALLY_EVALUABLE | Yes | No | None | Missing contradiction fact contract |
| `operational.job.lifecycle_inconsistent` | PARTIALLY_EVALUABLE | Yes | No | None | Missing inconsistency-evidence contract |
| `operational.job.follow_up_incomplete` | NOT_EVALUABLE | Yes | No | None | No authoritative follow-up lifecycle |
| `operational.location.required_data_missing` | PARTIALLY_EVALUABLE | Yes | No | None | Missing operational required-field policy |
| `operational.location.contact_condition_unresolved` | NOT_EVALUABLE | Yes | No | None | No authoritative condition lifecycle |
| `operational.location.service_restriction_active` | NOT_EVALUABLE | Yes | No | None | No Customer service-restriction authority |
| `operational.estimate.approved_workflow_not_advanced` | PARTIALLY_EVALUABLE | Yes | No | None | Missing duration and target-state policy |
| `operational.invoice.workflow_stalled` | PARTIALLY_EVALUABLE | Yes | No | None | Missing operational stall policy |
| `operational.payment.evidence_inconsistent` | PARTIALLY_EVALUABLE | Yes | No | None | Missing operational contradiction contract |
| `operational.workforce.assignment_ineligible` | PARTIALLY_EVALUABLE | Yes | No | None | Missing replayable assignment-time eligibility evidence |
| `operational.workforce.capability_requirement_missing` | PARTIALLY_EVALUABLE | Yes | No | None | Missing immutable Job capability-requirement identity |
| `operational.workforce.staffing_availability_mismatch` | PARTIALLY_EVALUABLE | Yes | No | None | Missing replayable assignment-time reconciliation evidence |

## API and lifecycle

Current admitted signals expose safe confidence, freshness, timestamps, policy,
limitations, quality digest, admissibility, and explanation metadata. Raw evidence
and conflict identities are not serialized. The read-only
`GET /api/v1/beacon/quality-semantics` endpoint exposes the 21-definition policy
matrix in Company/active-Branch context.

Existing expiration, clearing, acknowledge, review, snooze, and suppression
behavior is unchanged. Stale evidence cannot create an immortal signal: it is not
admissible and existing signal expiration still applies.

## Successor

The exact successor is `BANK.BEA.004 — Signal prioritization and tie-breaking`.
It remains separately owner-gated and is not started here.
