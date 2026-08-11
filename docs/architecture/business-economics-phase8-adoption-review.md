# External Phase 8 Adoption Review

Status: BE.REVIEW.1 — COMPLETE pending commit/push verification

Classification: TYPE A — Economics architecture/review/planning

## Decision boundary

This review evaluates external Business Economics Phase 8 commit
`49261468f443273ffefcf78d200048dccf097e0f` (`feat(economics): add
deterministic allocation and profitability engines`) for possible future use.
It does not approve or integrate that commit. Roadmap BE.8 remains the normative
[Version 1.0 Business Economics Contract](business-economics-v1-contract.md),
and the dependency and owner-gate semantics of the
[Business Economics Execution Plan](business-economics-execution-plan.md)
remain controlling.

The review conclusion is **selective adoption with modification only**. Pure
deterministic techniques may inform BE.12 and BE.13 after their dependencies and
owner decisions close. Neither module is a runtime or durable financial
authority, and neither may bypass BE.9–BE.11.

## Exact candidate inventory

The commit has parent `af06a7fa83364bc877edab81d18dae96e12de7d2`
(external Phase 7), changes six files, adds 1,115 lines, and contains no migration:

| File | Candidate content | Disposition |
| --- | --- | --- |
| `backend/app/economics/allocation_engine.py` | Immutable inputs/results and a pure deterministic allocation service | ADOPT WITH MODIFICATION in BE.12 |
| `backend/app/economics/profitability_engine.py` | Pure wrapper over Phase 6 computation, derived metrics, comparisons, digests | ADOPT WITH MODIFICATION in BE.13 |
| `backend/tests/economics/test_allocation_engine.py` | 18 allocation-policy/boundary/replay/failure tests | ADOPT WITH MODIFICATION as BE.12 evidence |
| `backend/tests/economics/test_profitability_engine.py` | 8 metric/replay/comparison/lineage tests | ADOPT WITH MODIFICATION as BE.13 evidence |
| `docs/architecture/business-economics-phase8-allocation.md` | Candidate architecture, invariants, persistence disclaimer | DEFER as historical evidence; BE.8 is normative |
| `docs/architecture/business-economics-foundation.md` | Eleven-line historical Phase 8 summary | DEFER as historical context |

There are no Alembic files, persistence adapters, database imports, APIs,
permissions, scheduler tasks, frontend files, provider credentials, or runtime
registration changes in the candidate.

## Capability disposition matrix

“Later adoption” always means a new, explicitly approved milestone after its
listed dependencies; it does not mean acceptance by this review.

| Capability | Observed behavior | Classification | Required future treatment |
| --- | --- | --- | --- |
| Frozen/slotted input and result records | Cost pools, policies, targets, lines, metrics, results, comparisons | ADOPT AS-IS LATER | Reuse the immutable pattern, subject to BE.8 field conformance. |
| Integer minor-unit allocation | Signed proportional division with deterministic remainder assigned in canonical target order | ADOPT AS-IS LATER | Retain exact balance and negative correction behavior in BE.12. |
| Stable UUIDv5 identities | Allocation, run, line, result, and comparison identifiers derived from SHA-256 payloads | ADOPT WITH MODIFICATION | Expand canonical manifests to every economically relevant field and version. |
| Canonical ordering | Targets, evidence, acquisition/allocation digests, explanations are sorted | ADOPT AS-IS LATER | Publish canonical schemas and golden replay vectors before BE.12/BE.13. |
| Evidence identity conflict rejection | Same source identity/version with different digest fails closed | ADOPT AS-IS LATER | Align identity tuple with authoritative ledger evidence and correction lineage. |
| Evidence freshness check | Policy-supplied maximum age rejects old evidence | ADOPT WITH MODIFICATION | Use source-specific approved SLAs; check future evidence and cutoff semantics. |
| Acquisition digest handling | Requires a 64-character value but excludes it from allocation identity | ADOPT WITH MODIFICATION | Validate hexadecimal SHA-256 and include digest in the canonical manifest. |
| Policy/run lineage | Emits policy/run references with versions, driver, input digest | ADOPT WITH MODIFICATION | Bind Finance approval, effective version, run authority, correction/reversal, and durable Phase 3 run identity. |
| Named allocation strategies | Direct, proportional, labor-hour, revenue-share, truck-day, technician, branch, company, fixed, custom | SUPERSEDED BY BE.8 | Names alone confer no policy authority; only BE.8/Finance-approved drivers may be enabled. |
| Strategy execution | Except direct-target cardinality, all named strategies use the same supplied weights | ADOPT WITH MODIFICATION | BE.12 must define per-strategy input/driver invariants or retain a single explicitly proportional primitive. |
| Direct allocation | Requires exactly one target | ADOPT WITH MODIFICATION | Also require authoritative direct linkage; a one-target weight is not attribution evidence. |
| Company isolation | Rejects targets from another Company | ADOPT AS-IS LATER | Retain and add durable tenant/authorization tests. |
| Branch isolation | Allows cross-Branch targets for Branch and Company boundaries | ADOPT WITH MODIFICATION | Company policies may cross Branches; Branch policies must remain inside the approved source Branch unless Finance explicitly defines a higher pool. |
| Circular allocation check | Rejects a target listed in source subject IDs | ADOPT WITH MODIFICATION | Replace shallow membership with a lineage graph check across source pools and prior runs. |
| Duplicate allocation check | Caller supplies prior allocation IDs | DEFER | Durable idempotency belongs to the ledger/allocation-run boundary; pure code cannot prove global uniqueness. |
| Currency behavior | Accepts ISO-like code then execution supports USD only | ADOPT WITH MODIFICATION | BE.8 remains single-currency per computation; supported currencies must be policy/configuration evidence, not hard-coded silently. |
| Measured confidence | Requires every measured cost pool/fact to have 100% confidence | SUPERSEDED BY BE.8 | Measured describes provenance, not certainty; preserve deterministic evidence-quality confidence separately. |
| Estimated allocation state | Output is always `ALLOCATED`, losing whether the pool was estimated | REJECT | State must preserve both allocation and actual/estimated basis without presenting an estimate as actual. |
| Allocation completeness/confidence | Line confidence copies pool confidence; completeness is min(pool,target) | ADOPT WITH MODIFICATION | Include driver confidence and explicit missing requirements; derive quality under an approved policy. |
| Allocation digest coverage | Omits periods, acquisition digest, completeness, target quality, policy effective dates/freshness, and correction lineage | REJECT | No candidate identity is authoritative until a complete canonical manifest is specified and tested. |
| Phase 6 computation delegation | Uses existing fail-closed facts/allocations service | ADOPT WITH MODIFICATION | Preserve the sole approved computation/materialization boundary and eliminate competing wrappers. |
| Gross/net reconciliation | Delegated service uses revenue − labor − materials − equipment − truck, then − overhead | ADOPT AS-IS LATER | Keep exact equations from BE.8; classify allocation roles before summation. |
| Contribution margin | Always copies gross profit | SUPERSEDED BY BE.8 | Label “V1 contribution margin (gross basis)” until Finance approves variable costs. |
| Margin percentages | Integer basis points; unknown on missing/zero revenue | ADOPT WITH MODIFICATION | Specify signed rounding and presentation separately from exact minor-unit reconciliation. |
| Allocated cost | Sums every allocation passed to wrapper | ADOPT WITH MODIFICATION | Define included roles and prevent duplicate/source-plus-allocation counting. |
| Fully burdened cost | Sums labor/material/equipment/truck/overhead then adds all allocations | REJECT | This may double-count allocations already included in components; BE.13 must derive from classified, non-overlapping components. |
| Profitability comparison | Like-scope actual/estimated and peer variance | ADOPT WITH MODIFICATION | Require matching Company, currency, period/cutoff, accounting basis, and comparable scope semantics, not only scope enum. |
| Explanation identities | Carries and sorts input explanation UUIDs | DEFER | Useful lineage, but deterministic owner-facing explanation contracts belong to BE.13/BE.17. |
| Digest format validation | Checks only string length for lineage digests | REJECT | Require lowercase canonical hexadecimal SHA-256 and content binding. |
| Authorization | No caller, permission, wage sensitivity, or projection access checks | DEFER | Authorization is an application boundary requirement before BE.11/BE.16; pure engines remain caller-agnostic. |
| Source ownership | Accepts already-acquired facts; does not write source domains | ADOPT AS-IS LATER | Preserve read-only ports and require BE.9–BE.11 source contracts. |
| Durable persistence | Explicitly absent; Phase 3 run persistence named as authority | DEFER | Compatibility must be proven before BE.12/BE.13; no schema change is authorized. |
| Tests | Strong examples for exact balance, replay, failures, metrics, and comparison | ADOPT WITH MODIFICATION | Convert to normative vectors, add omitted identity fields, authorization-boundary, quality, branch-policy, and non-double-counting cases. |

## Roadmap adoption map

| Roadmap milestone | Candidate contribution | Adoption boundary |
| --- | --- | --- |
| BE.9 | No implementation adoption | Candidate reveals contract questions only; BE.9 remains blocked by ACC.1/ACC.2/RPT.1/conditional IC.2 and source contracts. |
| BE.10 | Canonical ordering and conflict examples | Convert tests into source-conformance vectors; do not use candidate types as source authority. |
| BE.11 | Immutable read-only input pattern | Only after source mappings; candidate performs no acquisition or ledger materialization. |
| BE.12 | Allocation primitive, exact remainder, policy/run/evidence patterns, negative correction tests | Primary selective adoption point after Finance policies, full manifest, graph circularity, Branch rules, and durable-run compatibility. |
| BE.13 | Phase 6 delegation, metrics, comparisons, replay identities | Selective adoption after eliminating double counting, enforcing comparable contexts, quality semantics, and one materialization authority. |
| BE.14 | Checksums/replay concepts only | Candidate has no export, acknowledgement, correction, exception-owner, or GL reconciliation behavior. |
| BE.15 | Freshness and deterministic evidence concepts only | Candidate has no accounting periods, controlled reopening, close readiness, or audit package. |
| BE.16 | Result identity/quality fields may inform projections | Candidate has no API, authorization, sensitive-data policy, or Reporting/Mission Control contract. |
| BE.17 | Explanation IDs and evidence lineage may inform consumer contract | No Luminary/Beacon behavior, natural-language generation, recommendation, or rule adoption. |

## BE.8 unresolved-decision evidence and classification

The classifications below resolve readiness, not the substantive decisions.
Only D8 has a complete interim Version 1 answer in existing normative evidence.
No item is classified `DEFERRED`: every unresolved item is either needed by a
named Version 1 milestone or already has the normative interim rule described
below.

| ID | Decision | Available authoritative evidence | Missing evidence | First consumer | Classification |
| --- | --- | --- | --- | --- | --- |
| D1 | Payroll/paid-time authority and burden components | BE.8 declares future Workforce/payroll authority; Phase 5 separates paid and productive time | Named payroll owner/source, earnings/benefit/tax burden composition, effective rates, sensitive-data access | BE.9, then BE.11/BE.12 | EXTERNAL DEPENDENCY |
| D2 | Inventory costing and consumption effective date | BE.8 says consumption/returns, not purchases, produce Job material cost | Inventory authority, costing layer, return/transfer rules, effective timestamp | BE.9/BE.10 | EXTERNAL DEPENDENCY |
| D3 | Deposits, partial invoices, refunds, credits | BE.8 defines issued invoice accrual revenue and separate cash; Phase 2 keeps payments separate | Financial owner’s recognition/status matrix and adjustment effective dates | BE.9 | OWNER DECISION REQUIRED |
| D4 | Source-specific freshness SLAs | BE.8 requires an approved SLA and forbids a default; candidate proves a maximum-age mechanism | Per-source latency, cutoff, outage, grace, escalation, close-blocking policy | BE.10, operationally BE.15 | OWNER DECISION REQUIRED |
| D5 | Callback/warranty responsibility taxonomy | Jobs/Field own linkage; BE.8 requires original margin and quality cost visibility | Owning domain taxonomy, responsibility actor/reason, reclassification and correction rules | BE.9/BE.10 | EXTERNAL DEPENDENCY |
| D6 | Truck-day definition and fleet ownership | BE.8 permits direct trip cost or approved truck-day allocation; Dispatch supplies trip context | Fleet authority, day boundary, availability/use rules, shared vehicles, cost pools | BE.9/BE.12 | EXTERNAL DEPENDENCY |
| D7 | Overhead/marketing eligibility and drivers | Finance-approved pools and versioned Economics policies are required | Eligible accounts/spend, exclusions, direct vs pooled rules, driver hierarchy, effective dates | BE.12 | OWNER DECISION REQUIRED |
| D8 | Contribution-margin variable costs | BE.8 explicitly defines V1 contribution margin as gross profit until Finance approves another definition | Nothing required for V1 interim behavior; a later Finance policy may supersede it | BE.13 | RESOLVABLE NOW |
| D9 | QuickBooks export grain, acknowledgement, exception ownership | Phase 4 provider-neutral export/checksum/replay contracts; BE.8 preserves QuickBooks posting authority | Finance/provider grain, authoritative acknowledgement fields, rejection/correction owner and SLA | BE.14 | OWNER DECISION REQUIRED |
| D10 | Reporting materiality thresholds | BE.8 separates owner-attention materiality from exact zero-tolerance identities/arithmetic | Finance thresholds by report/period plus presentation and escalation policy | BE.14/BE.15 | OWNER DECISION REQUIRED |

D8’s implementation-ready rule is: compute contribution margin from the same
components and state as gross profit and present it only as **“V1 contribution
margin (gross basis)”**. It is not permission to create a different variable-cost
classification. All other decisions retain explicit missing/unknown behavior
until their named evidence and owner approval exist.

## Implementation-ready future specifications

These are bounded acceptance specifications, not implementation authority.

### Operational fact acquisition (BE.10/BE.11)

Each source envelope must include owning domain, Company, effective Branch when
applicable, stable record identity, source version, canonical SHA-256 evidence,
occurred/effective/observed timestamps, correction or reversal lineage, currency
and accounting basis for money, actual/estimated state, and authoritative scope
links. Adapters are read-only and deterministic. Missing data remains missing;
current assignment, date proximity, cardholder, or Customer similarity never
creates attribution. Replaying the same ordered source versions must produce the
same batch identity and evidence order. A conflicting identity/version/digest,
cross-Company value, unsupported basis/currency, future evidence, or stale value
under an approved source SLA fails closed.

### Allocation policy governance (BE.12)

An enabled policy requires Finance approval identity, immutable policy/version,
effective interval, Company and allowed Branch boundary, source pool
classification, actual/estimated basis, driver contract and source owner,
eligibility/exclusion rules, quality requirements, correction/reversal behavior,
canonical manifest version, and deterministic remainder rule. The manifest binds
all source and driver evidence digests, acquisition digests, periods, policy
fields, target identities/weights/quality, currency, and predecessor lineage.
Exact pool-to-line balance is mandatory. Branch policies cannot cross Branches;
Company policies may only cross Branches within one Company. Circularity is
checked across the lineage graph. Direct attribution requires source linkage,
not merely one target.

### Profitability materialization (BE.13)

One authoritative service consumes versioned ledger facts plus durable approved
allocation lines. It publishes Job, Technician, Branch, and Company analyses for
actual or estimated basis without mixing them. Components retain measured,
estimated, allocated, and missing provenance; allocation is orthogonal to basis.
Gross and net equations follow BE.8 exactly. Allocated cost is the sum of unique
included allocation lines. Fully burdened cost is the sum of non-overlapping
direct costs and approved overhead allocations; it must never add an allocation
already present in a component. Comparisons require matching Company, currency,
period/cutoff, accounting basis, compatible scope, and explicit basis labels.
Canonical inputs reproduce identities, values, evidence ordering, quality,
explanations, and digests.

### Reconciliation (BE.14)

Reconcile by Company, currency, basis, effective period, source type, and immutable
identity. Source representation, duplicates, evidence conflicts, allocation
balance, journal balance, known per-record amounts, deterministic remainder, and
QuickBooks accepted amount remain exact. Exported is not acknowledged; acknowledged
is not accepted unless provider evidence says so. Every rejection, correction,
replay, ownership mismatch, variance, and unexplained residual has an owner and
evidence. Reporting materiality may prioritize attention but never changes exact
integrity results.

### Close-readiness evidence (BE.15)

A close candidate names its responsible owner and immutable cutoff. It proves
source manifests complete under approved SLAs, allocations balanced, measurements
complete/current, corrections resolved, Economics and GL reconciliation current,
and audit-package digest complete. Unknown evidence blocks only the affected
declared gate but is never treated as zero. Time does not close a period. Late
facts require a reasoned, owner-attributed reopen transition; prior measurements,
projections, transitions, and audit packages remain immutable and linked to their
superseding versions.

### Reporting projections (BE.16)

Publish immutable analysis/projection identity, scope, period/cutoff, basis,
currency, revenue and cost components, gross/net/contribution values, confidence,
completeness, freshness, missing categories, integrity status, evidence lineage,
version, and responsible exception owner. Reporting and Mission Control format
these values but never recompute them. Unknown, estimated, allocated, stale, and
failed-integrity states remain visible. Wage-sensitive evidence is excluded unless
the consumer has an explicitly approved least-privilege contract. No projection
grants source editing, GL posting, close transition, Beacon rule, or Luminary
recommendation authority.

## Immediate durable work recommendation

After BE.REVIEW.1 is approved and pushed, **BE.EVIDENCE.1 — Source Authority
Evidence Matrix** can legitimately become the next READY candidate if the owner
provides an explicit Start and frozen source refs. It is TYPE A and does not need
ACC.2 or RPT.1 to inventory what evidence exists, what is absent, and who owns
each gap. It cannot declare BE.9 ready or choose financial policy.

BE.VECTORS.1 and BE.POLICY.1 are dependency-eligible after that matrix. The first
can define exact provider-neutral reconciliation/replay fixtures; the second can
prepare allocation-policy decision packets without selecting owners’ policies.
These milestones create durable value while BE.9 remains blocked and are defined
in the execution plan.

## Review conclusion

No BE.8 contradiction was found. External Phase 8 remains historical candidate
evidence. Selective future adoption is limited to pure deterministic techniques
and tests, chiefly in BE.12 and BE.13, after modification and owner approval.
The normative BE.8 contract, source ownership, Phase 3/4 durable authority,
QuickBooks boundary, exact reconciliation, and BE.PLAN.1 gates take precedence.

## References

- [Version 1.0 Business Economics Contract](business-economics-v1-contract.md)
- [Business Economics Execution Plan](business-economics-execution-plan.md)
- [Business Economics foundation](business-economics-foundation.md)
- [Phase 5 profitability contract](business-economics-phase5-contract.md)
- [Phase 6 deterministic computation](business-economics-phase6-computation.md)
- [Phase 7 acquisition boundary](business-economics-phase7-acquisition.md)
- [External Phase 8 architecture record](business-economics-phase8-allocation.md)
