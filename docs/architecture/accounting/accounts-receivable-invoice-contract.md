<!-- markdownlint-disable MD013 -->

# Accounts Receivable and Invoice Accounting Contract

- **Milestone:** `ACC.AR.CONTRACT.1`
- **Status:** Accepted implementation contract when this commit is authoritative
- **Runtime successor:** `INVOICE.1-3.ACCEL`
- **Accounting authority:** ACP after the separately approved cutover

## Authority and boundaries

This contract specializes the [Day-1 control contract](day-1-control-contract.md).
Invoicing owns invoice identity, immutable issued content, customer AR open-item
facts, credits, applications, and aging inputs. Accounting owns the chart of
accounts, book-basis policy, periods, posting rules, journals, control accounts,
and financial statements. Payments owns processor interactions, receipts,
refunds, settlement, and money movement. Customer, Jobs, Estimates, Price Book,
and Tax Policy remain authoritative for their existing records.

An invoice references, but never copies as mutable authority, one Company, one
Branch, one Customer, one Service Location, and optionally one Job and one
accepted Estimate revision. Invoice issuance snapshots the commercial evidence
needed to explain the obligation. Later source-domain changes do not rewrite an
issued invoice.

The current QuickBooks accounting basis must be recorded and accepted through
the Accounting policy/configuration owned by `ACC.CORE.1` before runtime invoice
posting is enabled. This contract deliberately does not choose cash, accrual, or
hybrid treatment. `ACC.POST.1` applies the accepted basis; the invoice subledger
retains the complete obligation and application evidence under every basis.

## Identity and aggregate

An Invoice has an immutable UUID and a gap-tolerant, never-reused,
Company-scoped human number. The Company and Branch are fixed at creation. The
aggregate owns:

- customer, service-location, optional Job, and optional accepted Estimate
  revision references;
- currency, issue date, due date, terms snapshot, customer-facing memo, version,
  and lifecycle/accounting statuses;
- immutable issued revisions containing ordered line snapshots and calculation
  evidence;
- append-only adjustments, credit memos, void/reversal evidence, applications,
  and accounting-handoff receipts; and
- creation, issuance, delivery, correction, and actor/correlation evidence.

Drafts may be edited by replacement of draft content under optimistic
concurrency. Issued content is never updated or deleted. Every issued revision,
credit, correction, application, and handoff has a stable source identity and a
Company-scoped idempotency identity. A reused key with different canonical input
fails closed.

## Lifecycle

The invoice lifecycle is independent from delivery and accounting-posting
progress:

```text
draft ──issue──> issued ──full application──> paid
  │                 │  ├──partial application──> partially_paid
  │                 │  ├──approved void──> voided
  │                 │  └──credits/write-off reducing open amount──> adjusted
  └──cancel──> cancelled

partially_paid / adjusted ──remaining applications──> paid
paid / partially_paid / adjusted ──compensating reversal──> prior derived state
```

`cancelled` applies only to a draft and creates no AR obligation. `voided`
applies only through explicit evidence to an issued unpaid invoice; it reduces
the open item through a full compensating invoice reversal and never deletes the
invoice. An invoice with any receipt application cannot be voided; reverse the
application first, then use credit/correction evidence. State is derived from
authoritative issue, credit, write-off, void, and application evidence. It is
not an independently editable balance flag.

Issuance requires a valid active Company/Branch scope, Customer and Service
Location relationship, at least one nonnegative line with positive quantity,
one currency, deterministic totals, an issue date, due date, terms, tax
evidence, and an idempotency key. The due date cannot precede the issue date.
Issue atomically freezes the revision, creates exactly one AR obligation, and
stages the invoice-issued event. Delivery failure does not undo issuance.

## Lines, totals, and EST.4

Invoice calculation consumes immutable snapshots; it does not recalculate an
accepted Estimate in place. Where an invoice originates from EST.4, it records
the accepted Estimate and revision identifiers, line snapshot/digest identities,
option selections, quantity, unit price, line total, allocated discount,
discounted basis, tax classification/policy/version/rate, tax, currency, and a
canonical calculation digest. The invoice may also originate from completed
Job evidence or authorized manual billing, but every line must state its source
kind and stable source reference.

All monetary values use fixed decimal storage. Runtime must use the existing
EST.4 cent rounding and deterministic remainder-allocation convention unless
Finance documents that current QuickBooks uses a different rule. The invariant
is:

`subtotal - discounts + tax + debit adjustments - credits - write-offs = invoice amount`

and:

`invoice amount - applied receipts - applied customer credits = open amount`.

Missing source, price, tax, or calculation evidence is an error, never zero.
Invoice generation must not silently bill unapproved Estimate options or infer
Job completion.

## Tax

Tax Policy remains authoritative for operational classification, effective
rate, and version. Issuance snapshots the policy evidence and per-line taxable
basis and tax. The sum of line tax equals invoice tax, and the invoice tax fact
submitted to Accounting equals the tax-liability posting basis exactly.

Tax corrections after issuance use a credit/reversal plus replacement evidence;
they never edit the issued tax snapshot. Filing, remittance, nexus policy, and
provider behavior remain outside Invoicing. A missing or ambiguous required tax
policy blocks issuance.

## Credits, corrections, voids, and write-offs

A customer credit is a customer-level AR asset available for application; a
credit memo is immutable invoice-linked evidence that reduces an AR obligation.
Credit issuance and application are separate idempotent actions. Applications
lock the affected open items and cannot exceed either available credit or open
invoice amount. Unapplication is a compensating record.

Corrections never mutate issued evidence. An amount correction creates a credit
memo (full or partial) and, when replacement billing is needed, a new invoice
linked to the corrected invoice. A duplicate-billing correction must prove which
obligation survives. Voids follow the lifecycle rule above. Negative invoices
are prohibited.

Day 1 includes controlled write-off evidence because AR aging and AR control
cannot reconcile if an approved uncollectible balance disappears. A write-off
requires a nonblank reason code, actor, effective date, open period, Finance
permission, amount not exceeding the open balance, and Accounting posting
receipt. Reversal is compensating evidence. Tax recovery treatment is not
inferred; it uses an accepted Accounting mapping/policy.

## AR subledger, aging, and control

The customer AR subledger is an append-only stream of obligation, debit
adjustment, credit memo, write-off, receipt application, unapplication, void,
and reversal entries. Every entry carries Company, Branch, Customer, currency,
source type/id/version, effective date, idempotency identity, actor/correlation,
and signed amount. Projections are rebuildable only from these entries.

For each Company, Branch, currency, and as-of instant:

- sum of open customer items equals the AR subledger balance;
- the AR subledger balance equals the Accounting AR control balance;
- every aging item traces to one issued obligation and all later applications;
- aging uses the contractual due date and accepted business timezone;
- unapplied receipts are excluded from AR aging and tracked by Payments/Accounting;
- negative open invoices and silent netting across customers, Companies,
  Branches, or currencies are prohibited; and
- unknown or missing posting evidence is reported as unreconciled, never zero.

Aging buckets are presentation policy supplied by Financial Reporting. The
authoritative aging inputs are issue date, due date, currency, original amount,
open amount, customer, Company/Branch, and as-of instant.

## Payment boundary

`PAY.1-3.ACCEL` owns receipt identity, processor references, authorization,
capture, refund/failure evidence, settlement, clearing, deposits, and unapplied
receipts. Invoicing accepts only an immutable, verified receipt fact and owns the
transactional application of an available amount to an invoice. It does not
call the processor.

An application is unique by Company plus payment receipt identity plus
application identity. It cannot exceed available receipt or invoice open amount.
Overpayments remain unapplied receipt liability/cash-accounting facts until an
explicit customer-credit conversion or refund occurs. Payment reversal/refund
does not delete an application; it creates application-reversal evidence and
reopens the invoice deterministically. Cross-customer application requires an
explicit authorized transfer contract and is not Day-1 implicit behavior.

## Business Events and Accounting handoff

Invoicing writes its aggregate, subledger evidence, and transactional Business
Event/outbox fact atomically. `ACC.POST.1` consumes events idempotently and owns
posting. The runtime packet must define these event contracts:

- `invoice.created`, `invoice.issued`, `invoice.voided`;
- `invoice.credit_memo_issued`, `invoice.write_off_recorded`;
- `invoice.payment_applied`, `invoice.payment_application_reversed`; and
- `invoice.correction_replacement_linked`.

Each posting event carries schema version, event/source identity, Company,
Branch, invoice/customer identity, effective date, currency, canonical amount
components, source version, calculation digest, correlation, and evidence
reference. It excludes sensitive payment instruments and mutable display data.

Accounting acknowledges a source event with a unique posting receipt containing
source event identity, posting status, journal identity/version, policy/mapping
version, posted/effective dates, and failure/reconciliation status. Invoice
`accounting_status` is derived as `pending`, `posted`, `reversed`, or
`reconciliation_required`; it never marks `posted` without a receipt. Posting
failure preserves the invoice and open item and blocks silent completion.
Invoice state and Accounting state cannot drift silently: reconciliation treats
any missing, duplicate, or contradictory receipt as an explicit exception.

## Isolation, authorization, and concurrency

All reads, writes, joins, uniqueness constraints, events, and applications are
Company-scoped. Branch-owned invoices require an authorized active Branch and
retain that Branch through every correction. Customer/Service Location,
Estimate, Job, tax policy, payment, and credit references must match Company;
operational references must also match Branch where their authority requires
it. Scope mismatch is indistinguishable from not found.

Runtime permissions are centralized and must separate invoice read, draft
management, issuance, credit/void/write-off, and payment-application actions.
Finance posting and approval permissions remain Accounting-owned. Issuance,
void, credit, write-off, and application operations require expected aggregate
version plus row locking of all monetary resources. Stale versions, ambiguity,
closed periods, contradictory replay, or missing authorization fail closed.

## Audit and retention

Every mutation records actor, effective/occurred timestamps, reason where
required, before/after state, source version, idempotency and correlation IDs,
and immutable evidence. Issued invoices, subledger entries, applications,
events, and posting receipts cannot be hard-deleted. Customer-facing document
renderings are reproducible from the issued revision. Retention follows the
Accounting control contract and legal policy; runtime cannot implement purge as
part of `INVOICE.1-3.ACCEL`.

## Dependencies and unresolved Finance inputs

The accepted EST.4, OPS.1, CRM.2, PLAT.1, COMMS.1, tax-policy, Price Book, Jobs,
and Business Event foundations satisfy domain dependencies. Runtime persistence
must serialize after `ACC.CORE.1` because the invoice posting receipt and period
controls depend on accepted Accounting interfaces.

Before invoice posting can be accepted, Finance must supply and approve from
current QuickBooks evidence: book basis, home currency and any multi-currency
use, invoice numbering/terms defaults, rounding convention if different from
EST.4, tax recovery/write-off mappings, AR control and revenue/tax/discount
account mappings, aging bucket presentation, and roles permitted to issue,
credit, void, and write off. Missing inputs block activation; they do not block
implementation of fail-closed contract scaffolding.
