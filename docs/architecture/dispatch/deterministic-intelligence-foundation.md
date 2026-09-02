# Deterministic dispatch intelligence foundation

Status: non-production proposal contract. Human dispatch authority remains decisive.

## Authority and contract

`dispatch.recommendation.v1` consumes authoritative Job scope/priority/window/duration, Workforce capability/certification/availability, schedule commitments, Fleet readiness, live field state, and evidence digests. It returns ranked placement proposals, constraint results, tradeoffs, limitations, schedule-risk conditions, recovery proposals, and a deterministic identity/digest. It cannot create, reschedule, assign, reassign, notify, or otherwise mutate operations.

Hard constraints evaluate Company, Branch, active/authorized Employee, capabilities, certifications, availability, appointment overlap, Customer promised window, Fleet readiness, Job lifecycle, and duration evidence. Unknown, stale, conflicting, policy-required, or external-gated hard evidence never becomes `PASS`.

Ranking is lexicographic rather than weighted: feasibility, unknown-hard-evidence count, downstream Customer-window risk, disruption, authoritative travel duration when present, start time, then stable Employee identity. This ordering preserves hard constraints and Customer commitments without choosing owner weights.

## Current readiness

- Customer windows, scheduled duration, Job priority/lifecycle, Workforce eligibility/capabilities/availability, appointments, Dispatch assignments, Fleet readiness evidence, and mobile progression are authoritative inputs.
- Scheduled duration is not historical measurement or prediction.
- Travel/routing is `EXTERNAL_GATE` until a provider-neutral routing adapter supplies origin, destination, departure/as-of time, duration/distance, provider/version, confidence, freshness, and evidence digest.
- Predicted Job duration and arrival remain future evidence authorities; no model is selected.
- Economics may later provide admitted Job opportunity context, but feasibility and Customer commitments must dominate and Employees must not be economically ranked.

## Schedule-wide intelligence

The engine examines existing commitments and downstream Customer windows, not only the new placement. Evidence-only conditions include `DOWNSTREAM_WINDOW_AT_RISK`, `ASSIGNMENT_CONFLICT`, `FLEET_READINESS_CONFLICT`, `CAPABILITY_EVIDENCE_MISSING`, `UNASSIGNED_HIGH_PRIORITY_JOB`, and `RECOVERY_OPTION_AVAILABLE`. Beacon receives only `evaluation_only` evidence and owns signal lifecycle.

Re-evaluation triggers include new/rescheduled/canceled appointments, new Jobs, en-route/arrival, Job start/pause/completion, early completion, running late, availability changes, Fleet unavailability, and Customer-window changes. A trigger recalculates evidence; it never mutates the calendar.

Recovery options are proposals: leave unchanged, accept an eligible placement, move later, or request Customer confirmation. Acceptance must call existing governed Scheduling/Dispatch commands. Rejection has no operational effect. A future append-only override contract may retain recommendation digest, bounded reason, actor, timestamp, and selected authoritative command identity; it must not score Employees or dispatchers.

## Visual and explanation contract

UI projections support a calendar ghost, recommended-slot highlight, risk marker, alternatives, and before/after preview. They supplement the existing visual calendar. Each candidate answers why this Employee/time, why another failed, what downstream risk exists, and what evidence is missing using named constraints—never an opaque score.

## Bounds and policy packet

Evaluation is capped at 50 candidates, 24 slots per candidate, and a 14-day horizon. Adapters must batch source retrieval; the pure evaluator performs no I/O or combinatorial schedule search.

Owner policy remains required for priority treatment beyond authoritative Job priority, travel and disruption weighting, overtime treatment, Customer-window flexibility, capacity buffer, economic-factor treatment, and any optimization tie-break beyond the published deterministic order. No defaults are activated.

Future provider-neutral seams: routing/travel prediction, Job-duration prediction, arrival prediction, and bounded schedule optimization. Every prediction must carry input/source digests, model/provider/version, as-of time, confidence, freshness, limitations, and deterministic evidence identity. Prediction never becomes source truth.
