# Invoicing and Payments Product Contract

- **Status:** Approved Version 1.0 product contract
- **Owner:** Financial for operational invoicing, payments, and reconciliation
- **Accounting authority:** QuickBooks

Architecture authority: [Operational Financial Boundary](../../architecture/financial/operational-financial-boundary.md)
and [QuickBooks Controlled Handoff](../../architecture/financial/quickbooks-handoff.md).

## Product outcome and boundary

ACP Enterprise records the operational amount owed for approved work, issues an
immutable customer invoice, safely records externally collected payments, and
exports controlled records for QuickBooks reconciliation. It does not implement
a general ledger, journal entries, accounts payable, bank reconciliation,
financial close, or financial statements.

Financial alone writes Invoice, Payment, Refund, Credit, Adjustment, export, and
reconciliation state. Jobs supplies versioned approved commercial scope and
completion/change-order facts. Sales supplies Estimate provenance. CRM supplies
identities. QuickBooks receives controlled export records and remains the
accounting system of record. Cross-domain table writes are prohibited.

## Invoice lifecycle

- `draft`: editable operational invoice assembled from approved scope;
- `issued`: immutable customer-facing issuance snapshot exists;
- `partially_paid`: settled net payments are positive but below balance coverage;
- `paid`: settled net payments and applicable credits cover the obligation;
- `voided`: issuance was nullified through an attributed append-only action;
- `written_off`: remaining operational balance was closed through an authorized
  append-only write-down record.

Draft creation copies approved Job commercial-scope snapshots. Draft edits must
not silently diverge from scope: additions, removals, price changes, or discounts
require a linked approved change order or an explicitly authorized adjustment
policy. Issuance assigns the Invoice number and freezes seller/customer display,
service location, lines, quantities, prices, discounts, tax decision, totals,
due date, terms, scope provenance, and document-rendering inputs.

An issued Invoice is never edited in place. Corrections use append-only credits,
adjustments, voids, write-downs, or a replacement document under an explicit
policy. `voided` and `written_off` are distinct: a void says the issued document
must not stand; a write-down says an acknowledged balance will not be collected.
Neither creates ledger semantics.

Number allocation is Company-scoped, atomic, unique, gap-tolerant, and never
reuses a number. Branch display prefixes may be configured without changing the
Company uniqueness boundary.

## Payment lifecycle

- `pending`: accepted command awaits confirmation or reconciliation;
- `recorded`: an externally collected payment has authoritative operational evidence;
- `settled`: evidence confirms funds are settled under the applicable method;
- `failed`: the attempt or external collection did not succeed;
- `partially_refunded`: settled value has been partly refunded;
- `refunded`: settled value has been fully refunded;
- `reversed`: the external financial institution or correction process reversed value.

Version 1.0 records externally collected payments. A provider-neutral command
contains Company/Branch, Invoice, amount, currency, method code, occurrence time,
external source, external reference, evidence reference, actor, correlation ID,
and idempotency key. It never stores raw card numbers, bank credentials, CVV,
payment-provider secrets, or unrestricted provider payloads.

Idempotency is enforced within Company and command type. A retry with the same
key and identical normalized input returns the original result. Reuse with
different input is rejected. When reliable, a normalized external source and
reference are additionally unique. Missing external references require stronger
evidence and actor attribution, not relaxed duplicate control.

Future payment links and direct charge providers implement the same normalized
command/result boundary. No provider is selected by this contract.

## Refunds, reversals, credits, and adjustments

Refund, reversal, credit, write-down, and adjustment records are append-only,
attributed, reason-coded, currency-consistent, and linked to the affected source.
A refund cannot exceed the payment's settled amount net of prior refunds and
reversals. A reversal records externally reversed value and is not relabeled as
a discretionary refund. An Invoice credit reduces the operational obligation;
it does not claim a QuickBooks journal entry. Negative Payments and destructive
amount edits are prohibited.

## Authorization proposal

| Permission | Purpose |
| --- | --- |
| `COMPANY_INVOICE_READ` | Read authorized Invoice and balance projections |
| `COMPANY_INVOICE_CREATE` | Create a draft from approved Job scope |
| `COMPANY_INVOICE_ISSUE` | Validate and issue an immutable Invoice |
| `COMPANY_INVOICE_VOID` | Void an issued Invoice with reason and attribution |
| `COMPANY_INVOICE_ADJUST` | Record authorized credits, adjustments, or write-downs |
| `COMPANY_PAYMENT_READ` | Read Payment and reconciliation projections |
| `COMPANY_PAYMENT_RECORD` | Record externally collected payment evidence |
| `COMPANY_PAYMENT_REFUND` | Record or initiate an authorized refund operation |
| `COMPANY_FINANCIAL_RECONCILE` | Review and resolve controlled reconciliation state |
| `COMPANY_QUICKBOOKS_HANDOFF_ADMIN` | Prepare, retry, and administer export batches |

These proposed codes do not modify the live catalog. Branch access and separation
of duties remain independently enforced.

## Proposed events

| Event | Safe payload core |
| --- | --- |
| `invoice.issued` | Invoice, Company/Branch, Job, customer, number, total, currency, due date, actor |
| `invoice.voided` | Invoice, number, controlled reason code, actor, replacement ID if any |
| `payment.recorded` | Payment, Invoice, amount, currency, method code, external-source code, actor |
| `payment.settled` | Payment, Invoice, settled amount/time, evidence reference |
| `payment.failed` | Payment/attempt, Invoice, controlled failure class and retryability |
| `payment.refund_recorded` | Refund, Payment, Invoice, amount, reason code, actor |
| `payment.reversed` | Reversal, Payment, Invoice, amount, controlled source/reason |

Events contain no raw payment credentials, unrestricted provider responses,
customer contact details, or sensitive evidence contents. The live event catalog
is unchanged by this milestone.

## Acceptance scenarios

1. Approved Job scope produces a reconciling draft and immutable issued Invoice.
2. One partial settled payment changes the Invoice projection to `partially_paid`.
3. Multiple distinct payments can satisfy one Invoice without duplicate recording.
4. Retrying an external-payment command returns the same Payment.
5. A partial refund reduces paid value without rewriting the Payment amount.
6. A full refund and an external reversal remain distinguishable.
7. Voiding an issued Invoice preserves its issuance snapshot and reason history.
8. Written-off value is separately visible from paid and credited value.
9. QuickBooks export state cannot change operational Invoice or Payment truth.

## Deferred work

Direct charging, payment links, gateway selection, card storage, bank feeds,
general ledger, journal entries, accounts payable, bank reconciliation, formal
statements, multi-currency conversion, and direct QuickBooks API integration are
deferred.
