# Operational source expansion for owner intelligence

Status: non-production, read-only composition. No source truth, Company policy, economic amount, Beacon signal, or operational mutation is created here.

## Admission audit

| Source contract | Classification | Admitted meaning | Explicit boundary |
| --- | --- | --- | --- |
| Customer equipment identity and Customer/Location/Job relationships | ADMISSIBLE | Typed, scoped identity and relationship evidence | No value, depreciation, cost, or free-text inference |
| Asset service/replacement actions | ADMISSIBLE when present | Equipment-associated service and replacement history | Association is not defect, callback, responsibility, or loss |
| Warranty evidence | PARTIAL | Warranty evidence exists | Eligibility, responsibility, corrective-work identity, and financial consequence remain SOURCE_REQUIRED |
| Fleet assignment/inspection/maintenance/out-of-service | ADMISSIBLE operationally | Fleet readiness and attention state | Fleet cost, lost revenue, capacity target, and productivity remain unavailable |
| Workforce capability/language/certification/availability | ADMISSIBLE operationally | Readiness evidence | No compensation, subjective score, or economic performance conclusion |
| Dispatch Employee/Job assignment | PARTIAL | Operational assignment | Not accepted Payroll-to-Job labor attribution by itself |
| Communications delivery lifecycle | ADMISSIBLE operationally | Prepared/sent/failed/ambiguous delivery state | No acceptance, payment, conversion, or revenue causality |
| Migration/native Accounting readiness | EXTERNAL_GATE | Safe readiness may be described | No raw QBO/HCP row; cash totals require admitted Accounting reporting authority |
| Capacity measurement | PARTIAL | Workforce availability and Fleet readiness are usable inputs | Complete Scheduling, Dispatch, Job completion, and labor attribution population remains required |

## Product contract

`economics.operational-source-readiness.v1` uses one bounded query per owning source, a maximum of 1,000 rows per source, Company scope, optional active-Branch scope, deterministic sorting, and a canonical digest. Output contains aggregate counts, safe opaque identities, evidence digests, readiness, limitations, owner questions, exception projections, Luminary findings, Beacon condition evidence, and the LIA explanation boundary. It contains no protected document, Asset serial/VIN, Employee identity or compensation, Customer contact, recipient, provider reference, Migration row, or monetary inference.

Luminary emits only useful exception/readiness findings. Beacon receives `evaluation_only` condition evidence and retains lifecycle authority. LIA may explain bounded evidence and limitations but cannot calculate, score, choose policy, retrieve protected sources, or mutate anything.

## Timing and correction

The projection period applies to operational actions and communications. Current scoped identity/readiness records are clearly distinct from the work, obligation, settlement, cash, and Accounting reporting periods. A later Customer/Vendor settlement, card payment, maintenance action, or communication does not rewrite historical Job Economics. Economics result and Luminary history retain their existing digest-bound successor contracts; this projection never edits prior evidence.

## Synthetic and adversarial acceptance

Qualification covers installed equipment with multiple service links, warranty evidence, maintenance due, Fleet attention, Workforce readiness, availability, a pending certification, sent and failed communications, incomplete Accounting readiness, and missing labor attribution. Negative cases keep equipment relationships cost-free, warranty non-authoritative for eligibility, delivery non-causal, Employee assignment non-causal, out-of-service non-monetary, and Accounting cash externally gated. Empty source populations become `SOURCE_REQUIRED`, not zero or ready.

## Luminary completion audit

| Capability | State |
| --- | --- |
| Economics profitability, comparisons, provenance, corrections | COMPLETE |
| Asset/Fleet operational readiness interpretation | COMPLETE |
| Workforce readiness interpretation | COMPLETE |
| Communications delivery interpretation | COMPLETE |
| Accounting readiness limitation | COMPLETE |
| Warranty/callback financial interpretation | SOURCE_REQUIRED |
| Full measured capacity Economics | SOURCE_REQUIRED |
| Cash-basis owner answers | EXTERNAL_GATE |
| Overhead allocation | POLICY_REQUIRED |
| Real-company owner workflow | OWNER_ACCEPTANCE_REQUIRED |

Shortest completion path: admit native Accounting reporting evidence; admit explicit callback/corrective-work identity and incremental-cost authority; admit complete productive-capacity and Payroll-to-Job attribution evidence; configure owner-approved allocation policy; perform real-owner acceptance over admitted ACP evidence. None of those gates permits a fabricated default.

## Future real-owner acceptance

Ask: how did we perform; what changed; which Jobs/services need inspection; what remains unpaid; what Vendor obligations exist; why profit and cash differ; which equipment has repeated service; which Assets/Fleet items need attention; what Workforce evidence is incomplete; which communications failed; which Accounting answers remain unavailable; what policy decisions remain; what evidence changed a result; and what should be inspected first. Each answer must expose its source, state, limitation, and next authoritative workspace without accessing raw Migration evidence.
