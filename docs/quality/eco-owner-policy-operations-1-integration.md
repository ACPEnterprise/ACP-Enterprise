# ECO owner policy operations and operator readiness

Date: 2026-09-12

- Protected starting authority: `8cf3bdbf0c814c4a45f2b189b061db556d1c704f`
- Protected reconciled authority: `9096a77705623409da1418022c7949cae08468ce`
- Composed prerequisite candidate: `f587c271318dec93dffe458c5c3892c7e79cb511`
- Candidate branch: `work/eco-owner-policy-operations-1`

## Operations boundary

`eco.owner-policy-operations.v1` supplies a typed application/service boundary
and repository protocol for listing policy families and history, drafting,
validation, submission, approval, and supersession. Each append-only operation
event preserves actor, timestamp, Company/Branch scope, policy version and
effective date, rationale/provenance, prior event digest, approval identity,
and immutable policy/event digests.

States remain distinct: `UNSELECTED`, `DRAFT`, `AWAITING_APPROVAL`, `APPROVED`,
and `SUPERSEDED`. Only explicitly approved policy snapshots can enter the
authoritative calculation engine. Draft validation uses the existing typed
policy contract; no default or Company value is selected.

Mutation operations reuse the existing permissions:

- `COMPANY_ECONOMICS_POLICY_DRAFT` for draft and submission;
- `COMPANY_ECONOMICS_POLICY_APPROVE` for approval and supersession;
- `COMPANY_ECONOMICS_POLICY_READ` for inspection and preview.

The repository is an adapter protocol with an in-memory qualification adapter.
The protected SQL policy table currently lacks `AWAITING_APPROVAL` and does not
represent all new break-even families. This candidate deliberately does not
force those events into the incompatible table or create competing authority.
A future protected persistence adapter requires Enterprise-approved schema
reconciliation before production wiring.

## Operator readiness

`eco.break-even-operator-readiness.v1` answers whether authoritative economics
can be calculated for the requested Company, Branch, service line, and period.
It returns `READY` or `BLOCKED` and groups exact reasons under:

- `EVIDENCE_MISSING`
- `EVIDENCE_CONFLICTING`
- `POLICY_UNSELECTED`
- `POLICY_UNAPPROVED`
- `ACCOUNTING_NOT_RECONCILED`
- `SCOPE_INVALID`
- `PERIOD_INVALID`
- `OTHER_GOVERNED_BLOCKER`

The accounting gate remains independently supplied. Until live intended-realm
QBO evidence is acquired and reconciled, callers must pass it as unavailable;
the readiness result remains `ACCOUNTING_NOT_RECONCILED` without redesign.

## Preview

Draft preview is explicitly labeled `ACTUAL_MEASURED`, `APPROVED_POLICY`,
`DRAFT_POLICY`, `SCENARIO_ASSUMPTION`, and `CALCULATED_PREVIEW`. Its wrapper is
always `authoritative = false`. It preserves baseline facts and approved policy,
and cannot mutate the repository or source evidence.

## Boundaries

No Production, QBO mutation, Accounting posting, Price Book repricing, Payroll
execution, employment action, autonomous selection, recommendation, or money
movement was performed. No schema migration is included.
