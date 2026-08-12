# Business Economics Reconciliation and Replay Vectors

Status: BE.VECTORS.1 — authoritative test-vector contract pending owner review

Classification: TYPE A — Documentation / contract

## Purpose and boundary

This contract defines synthetic, provider-neutral golden vectors for future
BE.10 source conformance and BE.12 allocation validation. It implements the
BE.VECTORS.1 definition in the
[Economics execution plan](business-economics-execution-plan.md) using the
[Version 1 Economics Contract](business-economics-v1-contract.md),
[source-authority matrix](business-economics-source-authority-evidence-matrix.md),
[source-readiness closure plan](business-economics-source-readiness-closure-plan.md),
and [external Phase 8 review](business-economics-phase8-adoption-review.md).

All values below are deliberately synthetic fixtures. They are not ACP business
facts, financial statements, policy decisions, source records, QuickBooks
entries, or permission to materialize anything. A vector describes an expected
deterministic result only after its named authoritative contracts exist.

This milestone adds no runtime, persistence, migration, API, frontend, provider,
Beacon, Luminary, Preview, Production, or operational accounting authority. It
does not begin BE.9, BE.10, BE.11, BE.12, or BE.13 and does not make any of them
READY.

## Normative semantics

### Source availability versus economic value

Source readiness and economic value are separate axes:

| Source state | Meaning in a vector | Permitted economic treatment |
| --- | --- | --- |
| `AVAILABLE` | The authoritative source contract supplies all required identity, scope, version, time, and evidence fields for the bounded fact | May yield a measured or estimated fact according to source meaning |
| `PARTIAL` | Some authoritative fields exist but required lineage/scope/version/correction/policy/value fields do not | Preserve supplied context; required economic fact remains missing |
| `ABSENT` | No authoritative source contract exists | Emit no numeric fact; missing is explicit and never zero |
| `CONFLICTING` | One authority/version identity has contradictory values or digests, or two incompatible authorities claim the fact | Reject/quarantine; do not select a winner |
| `NOT_APPLICABLE` | The record is a boundary/reference rather than an Economics acquisition fact | Do not ingest it as a business fact |

Economic component state is independently one of `MEASURED`, `ESTIMATED`,
`ALLOCATED`, or `MISSING`. Allocation provenance is orthogonal to actual versus
estimated basis: allocating an estimated pool does not make it actual. Confidence
describes deterministic evidence quality, completeness lists required categories
present, and freshness compares evidence with an approved source-specific SLA.
None substitutes for another.

### Authorities

- Jobs and Scheduling provide only the AVAILABLE context identified by
  BE.EVIDENCE.1; scheduled duration is not actual labor.
- Asset/Fleet is the future authority for equipment/vehicle identity,
  utilization, truck-days, operating periods, and costs. Workforce capability or
  proficiency is never utilization evidence.
- Workforce/payroll owns paid-time and burden evidence only after its protected
  source contract exists. Field/Operations owns productive Job time.
- Inventory/Field owns consumption and returns. A purchase is unassigned spend,
  not Job consumption.
- QuickBooks remains the Version 1 general-ledger and official accounting
  authority. Provider-neutral handoff vectors do not imply posting acceptance.

## Canonical envelope

Every source fixture uses this logical envelope. Optional fields are omitted,
never serialized as invented values.

```text
source_owner
source_system
record_type
record_id
source_version
company_id
branch_id (when authoritative)
occurred_at
effective_at
observed_at
currency + accounting_basis (for money)
actual_or_estimated_basis
authoritative scope links
correction/reversal/supersession predecessor (when applicable)
content_digest = lowercase hexadecimal SHA-256 of canonical source content
```

Canonical manifests use UTF-8 JSON, lexicographically sorted object keys, no
insignificant whitespace, uppercase ISO currency, integer minor units, RFC 3339
UTC timestamps ending in `Z`, ordered unique evidence by
`(source_system, record_type, record_id, source_version, content_digest)`, and
ordered targets by `(subject_type, subject_id)`. UUIDv5 identities are derived
only after the manifest binds every economically relevant field, including
period, basis, Company/Branch, source/acquisition digest, policy/effective
version, target weight/quality, and correction lineage.

A consumer must reject malformed or non-hexadecimal digests. Reordering
semantically unordered inputs must not change output ordering, values, identities,
or digests.

## Fixed synthetic identities

| Token | Synthetic value |
| --- | --- |
| `C1` | `10000000-0000-0000-0000-000000000001` |
| `C2` | `10000000-0000-0000-0000-000000000002` |
| `B1` | `20000000-0000-0000-0000-000000000001` |
| `B2` | `20000000-0000-0000-0000-000000000002` |
| `J1` | `30000000-0000-0000-0000-000000000001` |
| `J2` | `30000000-0000-0000-0000-000000000002` |
| `T1` | `40000000-0000-0000-0000-000000000001` |
| Period | `2026-01-05T00:00:00Z` through `2026-01-11T23:59:59Z` |
| Cutoff | `2026-01-12T00:00:00Z` |
| Currency/basis | `USD` / `accrual`, unless a vector says otherwise |

Evidence digests represented as `sha256("text")` mean the lowercase SHA-256 of
the UTF-8 bytes inside the quotes. Test implementations must calculate and bind
the digest; the notation is not a literal accepted digest.

## Golden vector catalog

Every vector has one expected terminal result: `ACCEPT`, `INCOMPLETE`, `REJECT`,
or `BLOCK_CLOSE`. `INCOMPLETE` is a valid explicit result, not an error and not a
zero value.

### Source and evidence vectors

#### SRC-01 — AVAILABLE Job context

- Input: Jobs-owned `J1`, version `7`, Company `C1`, Branch `B1`, Customer and
  Service Location links, status `completed`, effective/observed timestamps, and
  matching evidence digest.
- Expected: `ACCEPT`; one actual `job_context` fact, canonical evidence retained.
- Prohibited: generating revenue, labor, materials, equipment, truck, or overhead.
- Replay: identical envelope produces the identical fact identity and digest.

#### SRC-02 — AVAILABLE scheduled Appointment context

- Input: Scheduling-owned appointment version `3`, Company `C1`, Branch `B1`,
  explicitly linked to `J1`, with expected duration `120` minutes.
- Expected: `ACCEPT` as scheduled context only.
- Prohibited: treating `120` as productive time, paid time, equipment utilization,
  truck time, or any measured cost.

#### SRC-03 — PARTIAL Invoice

- Input: issued Invoice for `J1`, amount `100000` minor units, but no authoritative
  source version or correction lineage.
- Expected: `INCOMPLETE`; revenue component is `MISSING`, amount is absent, missing
  fields include `source_version` and `correction_lineage`.
- Prohibited: using adapter-derived status/time as proof of durable source version.

#### SRC-04 — ABSENT paid time

- Input: Technician `T1` exists, Job `J1` ran eight hours, but no Workforce/payroll
  paid-time source contract or record exists.
- Expected: `INCOMPLETE`; paid time and direct labor cost are `MISSING`.
- Prohibited: inferring paid time from Job duration, schedule, employee status, or
  productive time; missing never becomes `0`.

#### SRC-05 — ABSENT equipment utilization under resolved ownership

- Input: Workforce says `T1` is proficient with equipment type `camera`; `T1` is
  scheduled on `J1`; no Asset/Fleet asset or utilization record exists.
- Expected: `INCOMPLETE`; equipment utilization and equipment cost are `MISSING`.
- Prohibited: treating capability, schedule, assignment, proximity, Job presence,
  or generic overhead as utilization/cost. The stale Phase 4 Workforce binding is
  not source authority.

#### SRC-06 — PARTIAL purchase is not Job consumption

- Input: purchase of `50000` minor units has Company `C1`, cardholder `T1`, date
  within the Job period, and no authoritative Inventory consumption/Job link.
- Expected: `ACCEPT` only as unassigned purchasing context when the future
  Procurement contract exists; direct materials for `J1` remain `MISSING`.
- Prohibited: date, cardholder, Customer, assignment, or proximity attribution.

#### SRC-07 — contradictory evidence digest

- Input: two envelopes share `(source_system, record_type, record_id,
  source_version)` but carry `sha256("value-a")` and `sha256("value-b")`.
- Expected: `REJECT`; evidence conflict is zero-tolerance and named for source
  investigation. No fact or preferred digest is emitted.

#### SRC-08 — duplicate identity

- Input: the identical Invoice identity/version appears twice without explicit
  reversal or supersession.
- Expected: `REJECT`; duplicate count tolerance is zero.
- Replay distinction: retrying the same idempotent command returns the same
  result; presenting the same source twice in one authoritative set is a duplicate.

#### SRC-09 — cross-Company scope

- Input: request Company `C1`; evidence or target belongs to `C2`.
- Expected: `REJECT`; no rollup, comparison, allocation, or correction crosses
  Company boundaries.

#### SRC-10 — Branch attribution is source-effective

- Input: source-effective Branch is `B1`; Technician’s current/home Branch is
  `B2`.
- Expected: `ACCEPT` at `B1`; current employee or Customer Branch cannot restate
  history.

#### SRC-11 — actual and estimated bases remain separate

- Input A: accepted Estimate component `80000` with complete Sales/Price Book
  version lineage, basis `estimated`.
- Input B: issued Invoice component `100000` with complete Financial lineage,
  basis `actual`.
- Expected: two distinct components/analyses; estimate variance is `20000` only
  after both contracts are AVAILABLE. Actual computation never consumes A as an
  actual fact.

#### SRC-12 — freshness is parameterized, never invented

- Input: evidence age `49` hours; no approved source SLA.
- Expected: `INCOMPLETE`; freshness status is `unknown_policy`, not current or
  stale, and affected close readiness cannot pass.
- Parameterized continuation: with an approved versioned `48h` SLA, expected
  result is stale/`BLOCK_CLOSE`; with approved `72h`, expected result is current.
- Prohibited: BE.VECTORS.1 choosing either SLA.

### Correction and version vectors

#### COR-01 — effective reversal

- Initial fact: measured revenue `100000`, source version `1`, effective in the
  open period.
- Correction: append reversal `-100000`, version `2`, explicit predecessor
  version `1`, same Company/currency/basis and effective period.
- Expected: `ACCEPT`; historical version `1` remains; current net represented
  revenue is `0`; evidence and both versions remain ordered and traceable.

#### COR-02 — superseding correction

- Initial fact: measured cost `25000`, version `1`.
- Superseding fact: measured cost `24000`, version `2`, explicitly supersedes
  version `1` rather than adding to it.
- Expected: `ACCEPT`; current amount is `24000`; correction impact is `-1000`;
  version `1` remains historical and is not double-counted.

#### COR-03 — late evidence in closed period

- Input: authoritative late cost effective in a closed period, with no approved
  reopen transition.
- Expected: `BLOCK_CLOSE`/reject materialization into the closed period; preserve
  pending correction evidence.
- Continuation: after an owner-attributed, reasoned, versioned reopen transition,
  recompute affected scopes only and append new measurements/projections/audit
  package; never overwrite prior versions.

### Allocation vectors

Allocation vectors are acceptance evidence, not approved allocation policies.
The named synthetic policy exists only inside the fixture.

#### ALLOC-01 — exact proportional remainder

- Pool: `10001` minor units, Company `C1`, Branch `B1`, actual basis, complete
  source evidence.
- Targets in input order: `J2` weight `1`, `J1` weight `1`, third synthetic Job
  `J3` weight `1`.
- Canonical target order: `J1`, `J2`, `J3`.
- Expected lines: `3334`, `3334`, `3333`; sum `10001`; residual `0`.
- Replay with reversed input order: identical canonical lines, identity, digest,
  policy/run lineage, evidence order, and quality.

#### ALLOC-02 — negative correction remainder

- Pool: `-101`; canonical targets `J1`, `J2`, equal weights.
- Expected lines: `-51`, `-50`; sum `-101`; residual `0`.

#### ALLOC-03 — direct attribution requires source linkage

- Input: one target `J1`, but no authoritative direct link from the source cost.
- Expected: `REJECT`; cardinality of one is not attribution evidence.
- Continuation: with authoritative direct source linkage, allocate the entire
  amount to `J1` and retain that linkage as evidence.

#### ALLOC-04 — estimated pool preserves basis

- Input: estimated pool `9000`, approved synthetic policy, complete target driver.
- Expected: allocated provenance plus `estimated` basis; never relabel as actual or
  measured. Confidence cannot exceed the least-confident required source/driver.

#### ALLOC-05 — Branch and Company boundaries

- Case A: Branch `B1` pool targets `B2`; expected `REJECT`.
- Case B: Company `C1` pool targets Jobs in `B1` and `B2`, both Company `C1`, under
  an approved Company policy; expected `ACCEPT`.
- Case C: any target in `C2`; expected `REJECT`.

#### ALLOC-06 — circular lineage

- Input: target lineage ultimately contains the source pool identity, even though
  the immediate target ID differs.
- Expected: `REJECT`; circularity is evaluated over the lineage graph, not shallow
  target membership.

### Profitability and reconciliation vectors

#### PROF-01 — complete actual Job profitability

Synthetic actual measured inputs for `J1`:

| Component | Minor units |
| --- | ---: |
| Revenue | 100000 |
| Direct labor | 20000 |
| Direct materials | 10000 |
| Equipment | 5000 |
| Truck | 5000 |
| Approved allocated overhead | 10000 |

Expected exact outputs:

```text
gross_profit = 100000 - 20000 - 10000 - 5000 - 5000 = 60000
net_profit = 60000 - 10000 = 50000
gross_margin = 6000 basis points
net_margin = 5000 basis points
V1 contribution margin (gross basis) = 60000
allocated_cost = 10000
fully_burdened_cost = 20000 + 10000 + 5000 + 5000 + 10000 = 50000
```

Expected: `ACCEPT`, with all component evidence, allocation policy/run lineage,
actual basis, Company/Branch/period/currency, completeness, confidence, freshness,
and projection version. Operational net profit is not QuickBooks net income.

#### PROF-02 — missing direct component propagates unknown

- Same as PROF-01, but equipment source state is `ABSENT`.
- Expected: equipment, gross profit, net profit, margins, and fully burdened cost
  are `MISSING`/unknown; revenue/labor/materials/truck/overhead remain visible;
  completeness names equipment; no numeric profit is emitted.

#### PROF-03 — zero revenue denominator

- Complete inputs with revenue `0` and nonzero costs.
- Expected: gross/net profit arithmetic remains exact; gross/net margin percentage
  is unknown, never zero or infinity.

#### PROF-04 — allocated-cost non-double-counting

- Input: overhead allocation `10000` already appears in the overhead component.
- Expected: allocated cost is `10000`, fully burdened cost includes it once, and
  net profit subtracts it once. A wrapper that adds it again is `REJECT`.

#### PROF-05 — comparison compatibility

- Same scope kind but mismatched currency, Company, period/cutoff, or accounting
  basis.
- Expected: `REJECT` comparison. Matching context with different Jobs or matching
  `J1` actual-versus-estimated analyses is permitted with explicit labels.

### Accounting handoff and close vectors

These vectors validate boundaries only; unresolved Finance decisions remain
parameters and block operational use.

#### GL-01 — balanced provider-neutral journal

- Synthetic journal lines: debit `100000`, credit `100000`, matching Company,
  currency, period, source identities, branch dimensions and evidence checksum.
- Expected: handoff balance `0`, eligible for export preparation.
- Prohibited: labeling exported/prepared as posted or accepted.

#### GL-02 — unbalanced journal

- Debit `100000`, credit `99999`.
- Expected: `REJECT`; one minor unit exceeds the zero tolerance. Reporting
  materiality cannot waive the failure.

#### GL-03 — acknowledgement boundary

- Case A: export prepared, no provider acknowledgement; status remains
  `awaiting_acknowledgement`.
- Case B: authenticated provider acknowledgement explicitly accepts the immutable
  checksum/identity; status may become accepted.
- Case C: rejection or mismatched checksum; expected unresolved exception.
- The provider grain, evidence fields, and exception owner remain an owner/Finance
  decision for BE.14; this vector chooses none.

#### CLOSE-01 — complete open-period readiness

- Inputs: complete source manifest under approved SLAs, balanced allocations,
  complete/current measurements, no pending scopes, exact reconciliation, no
  unresolved corrections, named owner, immutable audit-package digest.
- Expected: readiness `ready`; time passage is irrelevant.

#### CLOSE-02 — missing or stale evidence

- Input A: required source is `ABSENT`; expected `BLOCK_CLOSE`, incomplete.
- Input B: evidence exceeds its approved source SLA; expected `BLOCK_CLOSE`, stale.
- Input C: no SLA is approved; expected `BLOCK_CLOSE`, freshness-policy missing.
- Prohibited: materiality, elapsed time, or a zero substitute clearing the gate.

## Deterministic replay manifest

For every accepted vector, a conforming implementation must prove:

1. identical semantic inputs in any permitted order produce identical canonical
   manifests, values, UUIDv5 identities, evidence ordering, allocation ordering,
   explanations, and SHA-256 digests;
2. a change to any economically relevant identity, version, amount, period,
   basis, currency, Company/Branch, evidence digest, policy version, target
   weight/quality, SLA version, or correction predecessor changes the bound digest;
3. retries return the existing idempotent result, while duplicates in an
   authoritative input set fail the zero-duplicate check;
4. corrections append lineage and affect only dependent scopes; and
5. rejected or incomplete vectors do not silently materialize numeric facts.

External Phase 8 identities are not accepted as authoritative golden outputs
because its reviewed manifests omitted required fields. BE.12/BE.13 may reuse the
technique only after the expanded manifest above is implemented and reviewed.

## Vector-to-roadmap traceability

| Vector group | Primary future consumer | Dependency still required |
| --- | --- | --- |
| SRC-01–SRC-12 | BE.10, then BE.11 | BE.9 approval, accepted source refs, source SLAs and authorization |
| COR-01–COR-03 | BE.10/BE.11/BE.15 | Authoritative correction contracts and period controls |
| ALLOC-01–ALLOC-06 | BE.12 | BE.11 facts, Finance-approved pools/drivers, BE.POLICY.1 and durable-run compatibility |
| PROF-01–PROF-05 | BE.13 | BE.12 approval, one materialization authority and persistence compatibility |
| GL-01–GL-03 | BE.14 | ACC.2 and Finance decisions on export/acknowledgement/exception ownership |
| CLOSE-01–CLOSE-02 | BE.15 | BE.14, approved SLAs, close owner and complete source manifest |

## Acceptance checklist

- Positive and negative minor-unit arithmetic is exact.
- Allocation remainders are deterministically assigned and residual is zero.
- Missing, partial, stale, conflicting, duplicate, cross-scope, and zero-denominator
  cases fail closed or remain explicitly incomplete as specified.
- Actual and estimated bases never mix; allocated provenance does not erase basis.
- Asset/Fleet and Workforce boundaries remain distinct.
- Company and Branch isolation follows source-effective scope.
- Evidence and corrections retain canonical lineage and deterministic replay.
- QuickBooks authority and exact reconciliation tolerances remain unchanged.
- Unresolved owner/Finance inputs are parameters or blockers, never fixture-derived
  policy.
- All fixtures are synthetic and cannot be represented as operational truth.

## Remaining blockers

BE.9 remains blocked by accepted source-domain contracts, `ACC.1 → ACC.2`, `RPT.1`
and conditional `IC.2`, owner/Finance decisions, collision analysis, and explicit
Start authority. BE.10 additionally requires approved BE.9 mappings, frozen source
refs, fixture-data policy, and source freshness rules. BE.12 requires BE.11 facts,
Finance pools/drivers, and BE.POLICY.1. This contract supplies validation evidence
only and clears none of those gates by itself.
