# ECO break-even input and operational diagnostics readiness

Date: 2026-09-12
Protected starting authority: `origin/customer-management-v1` at `150bcd2a4361313a2cac0337c0a1c85fbebac5c9`
Protected reconciled authority: `4514b5df6be66e50ee172085c622ae613e172086`
Candidate branch: `work/eco-break-even-efficiency-readiness-1`

## Scope

This successor composes the authoritative Workforce/Time/Economics evidence. It
does not recreate labor evidence, select an economics policy, calculate a
break-even rate, or authorize any mutation.

`eco.break-even-input-readiness.v2` deterministically reports:

- earned revenue and settlement readiness;
- actual direct-labor hours and accepted compensation/labor-cost authority;
- labor-burden prerequisites;
- direct material and material-costing prerequisites;
- other attributable direct costs;
- overhead/allocation prerequisites;
- productive hours;
- explicit Company or Branch scope and period;
- accounting/source reconciliation readiness.

Every fact retains evidence identities and digests, source authorities, source
dates when supplied, confidence, and limitations. States are `AVAILABLE`,
`PARTIAL`, `ABSENT`, `CONFLICTING`, or `NOT_APPLICABLE`. Missing evidence is not
zero. Accepted facts must share Company, Branch scope, and reconciliation key.

The v1 compatibility facts remain in the packet while the contract advances to
v2. No consumer outside tests currently invokes the builder.

## Operational diagnostics

`eco.operational-efficiency-diagnostics.v1` prepares bounded, immutable factual
components for utilization, travel, actual Job duration, callback/rework,
conversion, Dispatch, material leakage, overhead, capacity, and missing-evidence
analysis. It selects no threshold and makes no causal, Employee, pricing,
staffing, or operational recommendation.

Employee and Job identities may be preserved in admitted diagnostic evidence,
but the packet exposes no ranking or employment action. Scheduled time cannot
substitute for actual worked duration. Conflicting observations remain
conflicting.

## Current source readiness

This candidate establishes truthful contracts; it does not claim source
population that was not supplied to the builder. Based on protected contracts:

| Input | Contract readiness | Smallest live-data gate |
|---|---|---|
| Productive/direct labor hours | AVAILABLE when accepted Workforce/Job intervals populate the productive-hour packet | Accepted period-specific intervals |
| Earned revenue | PARTIAL/ABSENT until accepted earned-revenue evidence is supplied | Finance-accepted operational revenue basis |
| Settlement | PARTIAL/ABSENT | Accepted payment application/control reconciliation |
| Compensation/direct labor cost | PARTIAL/ABSENT | Effective-dated accepted compensation and paid-time costing |
| Labor burden | ABSENT unless approved prerequisites are supplied | Versioned approved burden method and authoritative components |
| Direct material | PARTIAL/ABSENT | Actual Job consumption plus accepted acquisition/cost-layer evidence |
| Material costing | ABSENT unless admitted | Authoritative costing basis; Price Book selling value is prohibited |
| Other direct cost | PARTIAL/ABSENT | Accepted Job-attributable source evidence |
| Overhead/allocation | ABSENT unless admitted | Accepted overhead pool plus approved allocation method |
| Accounting reconciliation | PARTIAL/ABSENT | Accepted reconciliation authority; QBO source-reporting alone is insufficient |

Real-company QBO OAuth remains owner-gated. No QBO state from the prior pushed
candidate was amended. Once production OAuth is available, the existing
read-only acquisition candidate can supply refreshed QBO source evidence; QBO
source reporting remains distinct from ACP accounting acceptance.

## Policy gates preserved

- break-even method and productive-hour definition;
- labor-burden method;
- overhead allocation method;
- target margin and Price Book markup;
- staffing and capacity-buffer policy;
- utilization, travel, duration, and conversion comparison thresholds/methods.

## Boundaries

No QBO mutation, Accounting posting, Production action, money movement,
repricing, Payroll execution, employment decision, model output, or autonomous
Luminary action is authorized or performed.
