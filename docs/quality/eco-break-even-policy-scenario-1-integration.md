# ECO break-even policy and scenario contracts

Date: 2026-09-12

- Protected starting authority: `d52d117801d72d04e81afac157671c97a941efa0`
- Composed prerequisite candidate: `d7ef88d1f969902d5d217fa56cb0218000c56741`
- Candidate branch: `work/eco-break-even-policy-scenario-1`

## Policy boundary

`eco.break-even-policy-contract.v1` supplies typed, immutable, effective-dated
owner/accountant selections for all required break-even policy families. Each
record carries Company/Branch scope, version, provenance and digest, approval
identity/role/time, rationale, effective interval, predecessor identity, and
content digest. Unselected policy carries no value or approval. Explicit
successors shadow predecessors for current evaluation without rewriting either
record.

There are no default All County values. A model snapshot is incomplete until
all policy families have one unambiguous effective approved selection.

## Scenario model

`eco.break-even-scenario-model.v1` keeps four output classes mechanically
separate:

1. measured facts with source authority and immutable digest;
2. approved policy inputs with versions and policy digests;
3. explicit scenario assumptions with rationale and provenance;
4. calculated results with formulas.

The deterministic model calculates measured contribution, contribution per
productive hour, break-even productive hours, break-even revenue, and
policy-target revenue comparisons. These are model outputs, not pricing,
staffing, margin, or employment recommendations.

Productive-hours, burden, labor, material, and overhead scenarios replace only
the named scenario value while preserving the original measured facts in the
result. Average-ticket or close-rate scenarios require explicit comparable
opportunity count plus both average-ticket and close-rate inputs; missing sales
evidence blocks the calculation.

## Fail-closed gates

- missing or unapproved policy;
- overlapping effective policy;
- missing or conflicting measurement;
- foreign Company or Branch;
- mixed measurement periods;
- duplicate measurement or scenario metric;
- non-positive productive hours or contribution;
- average-ticket/close-rate scenario without comparable opportunity evidence.

Authoritative zero remains zero. It is never treated as missing.

## Boundaries

No owner policy was selected. No Production, QBO mutation, Accounting posting,
Price Book activation or repricing, Payroll execution, employment action,
recommendation, or money movement is authorized or performed.
