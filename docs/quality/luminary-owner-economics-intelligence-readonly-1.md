# Luminary Owner Economics Intelligence Read-only 1

## Authority and prerequisite sweep

Starting protected authority: `b1bcca65c79164a699dc5e713dae44a10072b53b`.
Final reconciled protected authority: `a8a834c9ae2ed39cdb7bf18f8baa29910af799c3`.

| Prerequisite | Existing authority reused | Read-only conclusion |
|---|---|---|
| Business Economics | admitted immutable profitability results, workspace rollups, result history | Available for evidence-bound actual contribution and equal-period comparison |
| ECO source adapters | `eco.measurement.adapters.v1`, QBO and public operational adapters | Provider-neutral provenance retained; adapters do not promote source assertions |
| Source conformance | `ECO.SOURCE.CONFORMANCE.1` | Available/partial/unknown/conflicting remain deterministic; missing is not zero |
| Findings and measurement input | `eco.findings.v1`, `eco.measurement.inputs.v1` | Job/service/revenue/labor/material/policy gates are reusable without recalculation |
| Job/service readiness | authoritative Job, Customer, Branch identity joined through Economics | Available where admitted Job result identity reconciles; unclassified service remains partial |
| Revenue | admitted earned-revenue component | Available only in admitted immutable actual results |
| Settlement/payments | operational Payment/AR evidence remains distinct | Policy/source gated; not substituted for earned revenue or Accounting cash |
| Direct labor | admitted Job labor component | Available where accepted attribution reached Economics; Employee detail stays protected |
| Labor burden | Payroll provenance may exist | Independently explainable burden remains partial/owner-policy gated |
| Direct material | admitted Job material component | Available where Inventory/Purchasing costing was accepted; selling price is never substituted |
| Other direct cost | explicit equipment/truck components | Partial to available by admitted result; no miscellaneous cost inference |
| Overhead/allocation | Finance policy authority/readiness | Requires approved pools and allocation policy for fully loaded results |
| Accounting | admitted reconciliation lineage only | Native operational postings and source reports are not silently combined |
| QBO | `qbo-accounting-evidence/v1` seam | Real-company evidence remains external-gated until production OAuth/realm snapshot admission |
| HCP/source | provider-neutral source/admission contracts | Historical/partial/current authority remains labeled; raw Migration rows are not consumed |
| Estimates/Price Book | existing commercial surfaces | No direct admitted market/conversion/Price Book-item cost relationship in this projection |
| Invoices/Payments | existing authority | Distinct from earned revenue and settlement; no double counting |
| Inventory/Purchasing | existing source authority | Consumption/cost must be admitted through Economics before use |
| Workforce | protected accepted time/cost boundaries | Aggregate or Job-attributed labor only; no compensation disclosure or Employee ranking |
| Scheduling/Dispatch | operational readiness contracts | Assignment is not labor attribution; travel/capacity causality remains source-required |
| Customers | authoritative Job-to-Customer relationship | Cohort rollup supported; customer lifetime value is unsupported |
| Business Events | existing event infrastructure | Not invoked by the new read-only path |
| Beacon | existing condition identity/lifecycle | Reference and interpretation only; Beacon retains lifecycle ownership |
| LIA | existing `/lia/briefing` boundary | LIA may present Luminary truth; no circular calculation or mutation ownership |
| Existing Luminary | deterministic finding engine plus persisted briefing workflow | Reused conceptually; new owner projection is separate because persisted analyze/audit is not strictly read-only |

## Implemented contract

`luminary.owner-economics-readonly.v1` is served by `GET
/api/v1/luminary/owner-economics`. It performs scoped reads through the existing
Economics workspace and returns:

- Company/Branch/period economic facts with value, units, authority, confidence,
  completeness, evidence references, and projection timestamp;
- exact readiness and source-completeness classifications;
- deterministic read-only recommendation candidates only for complete admitted
  evidence;
- human decision packets;
- a causal boundary separating measured fact, co-movement, plausible cause, and
  recommendation;
- one-assumption-at-a-time hypothetical scenarios;
- market, workforce, Beacon, and LIA boundaries;
- an immutable packet digest and `mutation_authority = none`.

The service method performs no insert/update/delete, flush, commit, audit stage,
Business Event stage, command creation, or provider call.

## Supported and blocked scenarios

Supported when the admitted baseline is complete: price percentage, average-ticket
percentage, labor-efficiency percentage, and material-cost percentage. Arithmetic
is single-assumption and linear; actual baseline remains unchanged.

Close-rate scenarios require an authoritative comparable opportunity/conversion
population. Adding a truck requires Fleet-constrained capacity plus incremental
cost. Both return `INSUFFICIENT_EVIDENCE`; neither manufactures a result.

## Recommendation and decision boundary

The initial evidence-producing family is a pricing-review candidate for a Job with
negative admitted contribution. It explicitly states that negative contribution
does not establish underpricing and offers labor, material, scope, and service-mix
inspection alternatives. The contract registers operating-efficiency,
material/procurement, service-mix, sales/conversion, and cost-structure families,
but suppresses candidates until their exact evidence prerequisites exist.

No candidate is an instruction. Pricing activation, staffing, Employee action,
purchasing, Accounting, Payroll, payment, or operational commands require separate
owner-controlled domain authority that this contract does not possess.

## Exact unsupported questions

- Competitor price, market position, or market share without admitted market data.
- Customer lifetime value without sufficient longitudinal authority.
- Close-rate impact without authoritative opportunity and conversion populations.
- Truck/capacity impact without constrained-capacity and incremental-cost evidence.
- Fully loaded profit or break-even without approved policy and allocation inputs.
- Employee causality, ranking, discipline, compensation, or termination conclusions.
- Cash profit derived from Payment, settlement, or source-reported QBO alone.

## Next safe milestone

`LUMINARY.OWNER.ECONOMICS.REAL-EVIDENCE.ACCEPTANCE.1`: exercise this read-only
contract against owner-accepted current Company periods, validate individual
source gates, and accept or reject candidate usefulness without adding mutation or
new recommendation families.

## Qualification

- Broad affected backend suites (Luminary, Business Economics, Beacon, LIA,
  Operational Measurement, QBO source, Jobs, Payments, Inventory, Purchasing,
  Workforce, Scheduling, and Dispatch): 1,093 passed. One path-sensitive Payments
  test was rerun from its required `backend` working directory and passed.
- Focused Luminary and owner-intelligence suite: 28 passed.
- Fresh PostgreSQL zero-to-head: passed; one head/current=head
  `i9k1m3o5q7s9` on final protected authority; Alembic autogenerate drift: none.
- Backend Ruff, MyPy, Python compilation, diff, and protected-data scan: passed.
- Complete frontend suite: 473 passed across 125 files.
- Frontend ESLint, TypeScript, and production build: passed.
