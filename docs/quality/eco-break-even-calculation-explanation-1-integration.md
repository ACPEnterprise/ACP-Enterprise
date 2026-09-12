# ECO governed break-even calculation and explanation

Date: 2026-09-12

- Protected starting authority: `40f442530a3d0c52ab9926ad64fc87aa41bb8907`
- Protected reconciled authority: `27b89ecf1d702acbe75d0e1f95cf83c5f6bba5c9`
- Composed prerequisite candidate: `fe7a9623cb3ef40fd1cd4fe0d14253b2e95c1797`
- Candidate branch: `work/eco-break-even-calculation-explanation-1`

## Calculation contract

`eco.break-even-calculation.v1` combines immutable measured facts, one verified
effective policy snapshot, and optional explicitly versioned scenario
assumptions. It produces `AVAILABLE` or `BLOCKED` with exact reasons.

Available results include direct labor, burden, direct material, other direct
cost, allocated overhead, total operating cost, productive hours, effective
labor cost per productive hour, contribution and contribution margin,
break-even revenue and revenue per productive hour, gross-margin result, and
operating-margin result. Baseline/scenario packets include exact deltas.

Every result contains its formula and component traces. The enclosing packet
retains Company, Branch, service-line scope, evidence period and digests,
approved policy IDs/versions, scenario ID/version, and engine version. Scenario
components are labeled `SCENARIO_ASSUMPTION`; they never replace or rewrite the
baseline measured facts and are never described as actual performance.

Policy-dependent scope gates prevent Branch or service-line results unless the
approved policy permits that scope. The selected overhead allocation method is
recorded in the overhead formula. Missing policy/evidence, conflict, foreign
scope, mixed periods, and unsupported aggregation fail closed. Authoritative
zero remains distinct from missing.

## Explanation contract

`eco.break-even-explanation.v1` deterministically answers what changed, which
inputs caused it, how measured/policy/scenario values differ, what is missing,
why a result is blocked, and the smallest condition needed for availability.
It produces no recommendation or employment conclusion.

The owner policy-selection packet covers every supported policy family with
current selected/unselected state, why it matters, all contract-supported
options (with no preferred option), data prerequisites, and downstream effect.
It selects no All County policy value.

## Boundaries

No Production, QBO mutation, Accounting posting, Price Book repricing, Payroll
execution, employment action, recommendation, or money movement was performed
or authorized. No schema migration is required.
