# Dispatch Intelligence runtime composition

`dispatch.recommendation.v1` remains a deterministic proposal. The runtime
service composes scoped Job, Scheduling, Dispatch, and Workforce projections;
the engine does not query domain persistence and cannot write an appointment or
assignment.

## Current source admission

| Input | State | Runtime treatment |
| --- | --- | --- |
| Job lifecycle, priority, Branch, category | AUTHORITATIVE | Scoped Job detail projection |
| Appointment window and scheduled duration | AUTHORITATIVE | Scoped Scheduling projection |
| Customer requested/promised window | PARTIAL | Current appointment window is protected; a distinct promise contract remains source-required |
| Workforce active/Branch/capability/availability | AUTHORITATIVE | Workforce eligibility projection |
| Certification requirements | SOURCE_REQUIRED | No inference from notes or category |
| Current assignments and field arrival state | AUTHORITATIVE | Bounded Dispatch board projection |
| Working/paused/completed mobile progression | PARTIAL | Arrival is available; full field progression remains in owning field contracts |
| Fleet requirement and vehicle readiness | SOURCE_REQUIRED | Fleet is not required unless the Job has explicit requirement authority; unknown required evidence fails closed |
| Travel duration/distance | EXTERNAL_GATE | Never fabricated; recommendation remains useful with reduced confidence |
| Measured active Job duration | SOURCE_REQUIRED | Contract exists, but Job wall-clock lifecycle is not accepted as pause-corrected work duration |
| Economics | POLICY_REQUIRED | Excluded from rank; never used to rank Employees or override feasibility |

## Duration and routing boundaries

`dispatch.measured-duration.v1` accepts completed, pause-corrected source
evidence and produces bounded count, median, range, freshness, completeness,
and lineage by Company, Branch, category, and period. Its engineering safety
minimum is explicitly not an owner scheduling policy, and the aggregate is not
a prediction.

`dispatch.travel-evidence.v1` defines provider-neutral origin/destination
references, departure time, duration, optional distance, provider/model
version, freshness, limitations, and digests. No provider is selected or
called.

## Human and visual boundary

The protected API requires Job, Scheduling, and Dispatch read authority. It
returns a ghost-slot-compatible window, bounded alternatives, deterministic
constraints, risk evidence, and explanations. The Scheduling calendar remains
the command surface. Accepting a proposal must invoke the existing Scheduling
or Dispatch mutation command; the recommendation response declares
`mutation_authority: none`.

The contract is view-neutral and contains no pixel/layout semantics, so Day,
Week, Work Week, Month, and Dispatch views can project the same evidence.

## Re-evaluation and Beacon

The foundation publishes a bounded trigger catalog for Job, appointment,
assignment, field-state, availability, Fleet, Customer-window, and cancellation
changes. This milestone does not install an uncontrolled optimizer. Risk output
is `evaluation_only`; Beacon continues to own signal definition, priority,
assignment, snooze, resolution, and lifecycle.

## Owner policy and external decisions

Future policy authority is required for priority treatment, working hours,
slot granularity, travel/disruption weighting, overtime treatment, Customer
window flexibility, capacity buffer, and any Economics factor. External
routing and prediction providers remain unselected. HCP-derived records may be
consumed only after owning domains admit their mappings; missing assignment,
category, technician, duration, or optional context stays explicitly unknown.
