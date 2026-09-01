# Cash, Operational Obligations, and Business Economics

Status: non-Production provider-neutral composition authority

Contract: `economics.cash-operational-composition.v1`

## Three truths

ACP preserves three related but independent truth planes:

| Plane | Owns | Does not establish |
| --- | --- | --- |
| Business Economics | Admitted earned-work revenue, attributable Job cost, and contribution in the work period | Collection, bank movement, or Accounting recognition |
| Operational AR/AP | Invoices, open Customer and Vendor obligations, payment receipts, applications, disbursements, settlement and deposit workflow evidence | Cash-basis income/expense or Job economic cost |
| Accounting cash | Native Accounting recognition under the approved cash-basis chart/reporting authority | Operational fulfillment or earned-work profitability |

`WORK_PERFORMED`, `COMMERCIAL_INVOICE`, `OPEN_RECEIVABLE`,
`PAYMENT_ASSERTION`, `SETTLEMENT`, `CASH_RECEIPT`, `DEPOSIT`,
`EARNED_ECONOMIC_EVIDENCE`, and `ACCOUNTING_RECOGNITION` are distinct states.
No transition is inferred between them.

## Owner projection

`GET /api/v1/business-economics/cash-operational?start=...&end=...` is a
read-only, Company/Branch-scoped projection. It requires explicit Economics,
Invoice, Payment, AP-report, and Accounting-report read permissions before any
cross-domain query runs. It combines:

- immutable admitted Economics results for the selected work period;
- native current open Invoice balances for Jobs completed in the selected work
  period;
- native payment-receipt and deposit-batch workflow evidence;
- native open AP bills and recorded Vendor disbursements;
- only the active Accounting chart's basis/currency readiness.

The projection deliberately returns Accounting recognized income and expense as
unavailable until a native admitted Accounting report supplies them. It does not
substitute payment receipts, settlement, deposits, Invoices, AP bills, or
Migration records.

Open obligation amounts are current operational state for the bounded source
population. They are not reconstructed historical aging balances. ACP does not
infer collection or aging thresholds.

## Timing invariants

- Customer payment after the work period changes settlement/cash-period evidence,
  not the historical Job contribution.
- Vendor payment after material consumption changes obligation/cash evidence, not
  the Job material cost.
- A credit-card purchase can establish an obligation; card settlement and bank
  outflow are later facts and cannot recreate the cost.
- A Service Agreement enrollment or billing-ready state is not revenue.
- A Purchase Order is not expense; receipt is not payment; Inventory movement is
  not bank outflow; material consumption requires admitted Job-cost authority.
- Payment assertion is not settlement. Settlement is not deposit. Deposit is not
  Accounting recognition.

## Luminary, Beacon, and LIA

Luminary may deterministically explain a timing relationship only from admitted
evidence and must use association/timing language rather than causality. Beacon
readiness is exposed without creating a signal; an approved Beacon definition
and threshold remain required. LIA receives a digest-bound, read-only envelope
that contains state and limitations, not protected source rows or amounts.

## Migration boundary

Migration owns real QBO/HCP acquisition, reconciliation, and Accounting
admission. Economics consumes only safe authority/readiness metadata and native
admitted domain contracts. It never reads protected Migration evidence or
interprets real provider rows.

## Operator interpretation

When the three cards differ, do not reconcile them by editing or assuming a
value. Inspect the owning domain:

1. Work performed: inspect admitted Economics lineage and missing Job evidence.
2. Still owed: inspect native Invoice/AR or AP workflow under its own permission.
3. Cash-basis Accounting: inspect admitted native Accounting reports after
   Migration/Finance admission.

Until Accounting report evidence is admitted, "How much cash did we collect?"
must remain unavailable even when payment receipts or deposits exist.

## Remaining policy and source gates

- admitted native cash-basis Accounting report totals;
- owner-approved collection/attention thresholds before Beacon signals;
- authoritative historical as-of AR/AP snapshots for historical-aging answers;
- provider/card-liability classification where native authority does not already
  establish it;
- real Migration evidence admission, owned outside ECO.

No schema change, provider call, Accounting posting, payment execution, Preview
deployment, or Production operation is part of this contract.
