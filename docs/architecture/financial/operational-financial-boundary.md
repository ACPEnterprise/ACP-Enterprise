# Operational Financial Boundary

- **Status:** Approved Version 1.0 architecture contract
- **Operational owner:** Financial
- **Accounting system of record:** QuickBooks

## Authority

ACP Enterprise is authoritative for operational Price Book snapshots, approved
Job commercial scope, Invoice documents, Payment/Refund evidence, operational
balances, and handoff status. QuickBooks is authoritative for accounting books
and reports. Neither system silently overwrites the other's authority.

The Financial domain owns Invoice, Payment, Refund, Credit, Adjustment,
Write-down, export-batch, and reconciliation aggregates. Sales owns Estimates;
Jobs owns commercial scope and materials used. Financial repositories never
write Sales, Jobs, CRM, or accounting-integration tables owned by another module.

## Decimal and currency representation

- Money uses base-10 decimal arithmetic. Binary floating point is prohibited.
- Every monetary aggregate has one ISO 4217 uppercase currency code. Version 1.0
  does not convert currencies or mix currencies within an aggregate.
- Persisted money supports at least `NUMERIC(18, 4)`. Customer-facing USD document
  totals use currency scale 2. Higher internal precision is retained until the
  defined rounding boundary.
- Quantities support at least `NUMERIC(18, 6)` and must be greater than zero for
  ordinary commercial lines. Reversing records use an explicit operation type,
  not an illicit negative quantity.
- Unit prices use money scale 4. An extended amount is quantity multiplied by
  unit price, rounded once to the currency scale using round-half-even unless a
  configured jurisdiction rule explicitly requires another recorded mode.
- APIs and events serialize decimal values as canonical strings. They never use
  JSON floating-point numbers as the authority.

Configuration records the currency scale and rounding mode used by each snapshot.
Changing configuration never recalculates an existing snapshot.

## Calculation order

For each line:

1. calculate the unrounded product of quantity and unit price;
2. round the extended amount at the controlled line boundary;
3. calculate authorized line discount and clamp only by rejecting invalid input;
4. derive the nonnegative net line amount;
5. determine taxable basis from net amount and tax classification;
6. calculate tax using the recorded Company/Branch tax decision;
7. retain line results and sum the already-rounded controlled amounts.

Aggregate discounts, if permitted by configured policy, are allocated
deterministically across eligible lines so taxable basis and future credits can
be reproduced. Allocation remainder follows a stable order such as line
position then line ID. The applied policy and allocation are snapshotted.

The Version 1.0 tax calculator receives Company, Branch, jurisdiction-effective
configuration, tax-classification snapshots, taxable bases, and effective time.
It returns normalized rule references, rates, per-line tax, aggregate tax, and
rounding metadata. A future external provider must implement this interface and
return reproducible normalized evidence; provider payloads do not become domain
state.

## Amount definitions and invariants

- `gross_line_amount`: rounded quantity × unit-price result before discounts;
- `discount_amount`: authorized reduction, never negative and never greater
  than its eligible basis;
- `net_line_amount`: gross line amount minus line and allocated discounts;
- `taxable_basis`: nonnegative eligible net amount;
- `subtotal`: sum of net line amounts before tax;
- `tax_amount`: sum of controlled line tax amounts;
- `issued_total`: the immutable issued subtotal plus issued tax and any
  issuance-time authorized charges;
- `adjusted_obligation`: issued total plus post-issuance positive adjustments,
  minus credits and write-downs;
- `paid_amount`: sum of settled payments and externally collected payments whose
  recorded method policy makes them eligible for balance;
- `refunded_amount`: sum of valid append-only refunds;
- `credit_amount`: sum of valid Invoice credits;
- `adjustment_amount`: separately summed authorized operational adjustments;
- `net_paid_amount`: paid amount minus refunds and reversals;
- `balance_due`: max of zero and adjusted obligation minus net paid amount.

Overpayment is represented explicitly as unapplied/overpaid value; it is not
hidden by the nonnegative balance projection. The following always hold:

- currency codes match across every contributing amount;
- subtotal, tax, issued total, paid, refunded, credits, adjustments, write-downs,
  unapplied value, and balance reproduce from append-only components;
- no discount, refund, credit, or write-down exceeds its remaining eligible basis;
- a Payment amount is positive and immutable;
- refunded plus reversed value cannot exceed eligible settled value;
- paid and written-off are never conflated;
- voided documents retain their original totals but do not present an active
  collectible balance;
- contradictory totals fail the command and produce no partial state or event.

## Discounts and authorization

Discount authority is configured by Company and optionally narrowed by Branch,
permission/role assignment, discount type, amount or percentage bands, and
effective interval. No percentage or dollar threshold is hard-coded. The domain
records the policy version evaluated, requester's calculated authority, requested
discount, and any separately attributed approval.

An approver cannot approve outside their own effective authority. Self-approval
is allowed only if an explicit policy says so. Policy changes are prospective
and do not invalidate previously approved snapshots.

## Snapshots and recalculation

Price selection, Estimate readiness/presentation, Estimate approval, Job-scope
establishment, and Invoice issuance each create an immutable boundary snapshot.
A downstream snapshot copies the exact upstream identity/version and controlled
values it relies on.

Drafts may be recalculated only through an explicit command using a declared
effective time and expected concurrency version. Recalculation creates a new
revision when customer presentation or approval evidence already exists.
Issued Invoices, approved scope versions, Payments, Refunds, and reconciliation
records are immutable. Corrections append compensating domain records.

## Invoice and Payment state projections

Lifecycle values are defined in
[Invoicing and Payments](../../product/modules/invoicing-and-payments.md).
Lifecycle status is a controlled projection of append-only facts where practical.
Commands validate both the requested transition and the underlying amounts.
Changing a status field alone can never settle a Payment, pay an Invoice, perform
a refund, void a document, or write down a balance.

## Event-catalog compatibility

The live catalog already reserves `estimate.created`, `estimate.presented`,
`estimate.approved`, `estimate.declined`, `invoice.created`,
`payment.received`, and `payment.refunded`, primarily for the current foundation
and migration behavior. Those names and their historical events remain valid.
The operational proposal adds the more precise lifecycle events documented by
this milestone:

- `price_book.price_version_activated`;
- `estimate.expired`;
- `job.commercial_scope_established`;
- `job.change_order_approved`;
- `invoice.issued` and `invoice.voided`;
- `payment.recorded`, `payment.settled`, `payment.failed`,
  `payment.refund_recorded`, and `payment.reversed`;
- `quickbooks.export_prepared`, `quickbooks.reconciliation_completed`, and
  `quickbooks.reconciliation_failed`.

Catalog integration must define `payment.received` and `payment.refunded` as
legacy/general facts and the new names as operational lifecycle facts. Producers
must not emit both for one transition unless a reviewed compatibility projection
has a single deduplication identity. Analytics and Beacon must be updated under
their own ownership to consume canonical facts without double-counting. The
existing `invoice.created` event represents draft identity creation and never
substitutes for immutable `invoice.issued`.

## Existing migration persistence compatibility

The current `financials` models contain migration-oriented Estimate,
EstimateLineItem, Invoice, InvoiceLineItem, and Payment rows. Their current
status and amount constraints are evidence of imported source facts, not the
approved operational aggregate contract.

Implementation must first choose one reviewed compatibility strategy:

1. retain imported tables/rows as a legacy projection and create new operational
   aggregates with explicit source links; or
2. evolve tables additively with record-kind, provenance, evidence-completeness,
   revision, and lifecycle support while preserving all imported identities.

Destructive reinterpretation is prohibited. Existing source-identity mappings
and migration orchestration remain valid. Imported rows carry provider, source
ID, source artifact/run, imported-at time, transformation version, confidence,
incomplete-data flags, and raw-evidence references where allowed. They default
to read-only historical behavior unless they pass an explicit adoption command
that supplies missing operational evidence and preserves original provenance.

Migration must not manufacture presentation, approval, issuance, settlement,
refund, or reconciliation evidence. An imported `approved`, `issued`, `paid`, or
`refunded` label is a source-reported state with declared confidence until
reconciled. Operational commands cannot use incomplete historical rows as though
ACP Enterprise had performed the original action.

## Luminary seam

Luminary is the Business Economics and Profitability Intelligence layer, not an
AI persona and not an authoritative financial ledger. It consumes versioned,
tenant-scoped projections and events for approved revenue, issued revenue,
settled cash, discounts, tax, credits, refunds, materials used, labor/capacity,
callbacks, and other approved costs. It explains provenance and freshness and
never writes operational or accounting facts.

Profitability is unavailable—not zero—when required cost or revenue inputs are
missing. Luminary implementation follows operational correctness and QuickBooks
reconciliation.

## Validation obligations

Runtime implementation requires PostgreSQL constraint tests, empty-chain and
upgrade migration tests, decimal property/boundary tests, concurrency and
idempotency tests, tenant/Branch authorization tests, event atomicity tests,
and reconciliation fixtures. This documentation milestone makes no runtime claim.
