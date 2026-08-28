<!-- markdownlint-disable MD013 -->

# ACC.IC.1 Accounting Integration Candidate

## Boundary

ACC.IC.1 is the immutable provider-neutral handoff between reconciled source
evidence and a separately authorized ACC.MIG.1 execution. It creates no journal,
changes no balance, contacts no provider, and grants no rehearsal authority.
The serialized candidate is the durable content-addressed handoff unit; the
included registry is deliberately an in-memory reference implementation for
tests and callers, not a claim that process memory is durable custody.

No new database table is required. A future rehearsal must place the canonical
bytes in an approved immutable evidence store and bind that stored digest to its
separately approved execution record. Existing native journals, approvals,
audit records and Business Events remain the authority only after ACC.MIG.1 is
separately invoked.

## Canonical content

`AccountingIntegrationCandidate` is frozen and serializes as normalized UTF-8
JSON with sorted object keys, stable tuple ordering, ISO dates/timestamps,
lowercase UUID text, and exact fixed-point decimal text. SHA-256 covers every
material field except the digest field itself. Identical inputs therefore yield
identical bytes and digest; any scope, evidence, policy, mapping, amount, actor,
time, state or lineage change produces a new digest.

The package binds candidate/version/lineage identity, Company and Branch scope,
schema and definition versions, source authority/package/digest, sanitized
custody references, reconciliation digest, policy and mapping references,
cutover date, period, currency, expected balanced totals, actors, timestamps,
exceptions, state and canonical digest. It contains no raw provider records,
credentials, tokens, bank details or processor payloads.

## Acceptance lifecycle

The canonical states are `DRAFT`, `INCOMPLETE`, `RECONCILIATION_REQUIRED`,
`FINANCE_REVIEW_REQUIRED`, `OWNER_REVIEW_REQUIRED`,
`ACCEPTED_FOR_REHEARSAL`, `REJECTED` and `SUPERSEDED`. Candidate construction
never infers approval from source presence. Missing references yield
`INCOMPLETE`; unresolved reconciliation yields `RECONCILIATION_REQUIRED`; a
complete reconciled package begins at `FINANCE_REVIEW_REQUIRED`.

Finance and owner transitions require independent actors. Acceptance only means
the package is structurally and evidentially eligible to be proposed for a
future rehearsal: `RehearsalReadiness.authorization_granted` is always false.
Rejection and supersession produce new state-bound digests. A correction uses a
new identity and next version with an explicit `supersedes_candidate_id`; the
prior candidate is preserved as `SUPERSEDED`. Exact replay is idempotent and a
reused identity with different content is rejected.

## Policy and custody gates

No Finance default exists. Explicit references are required for opening-state
acceptance, reconciliation precedence, retained earnings, opening equity,
unresolved AR, unresolved AP, cash/bank differences, materiality, cutover,
period, currency, chart/account mappings, AR/AP controls and cash/bank mapping.
The source package identity, manifest digest, authority classification,
reconciliation digest and custody references must agree with ACC.MIG.1 evidence.

Real HCP/QBO evidence, the outstanding balance assertions, live balances,
Preview, Production, rehearsal and cutover all remain outside this milestone.
