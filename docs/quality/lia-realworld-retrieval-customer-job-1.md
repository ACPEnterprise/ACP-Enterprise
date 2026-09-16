# LIA Real-World Customer and Job Retrieval 1

## Authority and diagnosis

Starting protected authority: `90af57abf5f4e2dbda75ed2680d4d420eb60410c`.
The protected Employee-name repair is already authoritative. Existing Customer
and Job context projections were suitable for reuse, but natural lookup stopped
before them:

- Customer names had no exact, authorization-scoped LIA subject resolver.
- Job references selected the Jobs source but were never resolved to the native
  Job identity required by `JOB.LIA_CONTEXT.v1`.
- Customer context did not summarize authorized Appointment or Payment states.

## Bounded behavior

- `Show me Customer <exact name>` resolves only the exact normalized native ACP
  Customer name within Company and authorized Branch evidence.
- `Show me <name>` checks exact authorized Customer and Employee identities. A
  unique result resolves; cross-type or same-type collisions are ambiguous.
- `Show me Job <reference>` resolves only a canonical native ACP Job number.
  Numeric shorthand is deterministically normalized to the existing
  `JOB-000000` convention.
- No fuzzy/source-system identity matching is used.
- Zero and multiple matches return existence-hiding unavailable/ambiguous
  responses before projection retrieval.
- Follow-ups retain the server-resolved opaque Customer or Job identity,
  authorization version, evidence digest, and source topics.

The existing `CUSTOMER.LIA_CONTEXT.v1` projection supplies authorized Customer,
Location, Job, Estimate, Invoice, Agreement, Appointment-state, and
Payment-state evidence. The existing `JOB.LIA_CONTEXT.v1` projection supplies
Customer, Location, lifecycle, Appointment, Dispatch, Estimate, Invoice, and
Payment evidence. Missing permissions remain explicit limitations. Neither
projection exposes payment instruments, protected Payroll fields, raw notes, or
source-system identity guesses.

## Qualification

- LIA, Customer, and Jobs suites: 316 passed against fresh PostgreSQL.
- Focused natural retrieval and follow-up acceptance: 26 passed.
- Ruff, MyPy, and Python compilation: passed.
- Fresh migration to the existing single head `l2n4o6q8s0u2`: passed.
- No schema change was introduced by this milestone.
- No mutation command, action proposal, voice surface, or provider dependency
  was added.

Live owner acceptance requires an integrated Preview release and an authorized
known Customer name. `JOB-000306` is a suitable existing real-world Job lookup
candidate; this milestone does not modify it.
