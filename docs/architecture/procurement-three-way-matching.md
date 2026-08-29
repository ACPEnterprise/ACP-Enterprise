# Procurement three-way matching authority

The native procurement match compares immutable Purchasing and Accounts Payable evidence. It does not rewrite a Purchase Order, receipt, return, Vendor Bill, Inventory movement, or Accounting fact.

## Authority and admission

- Purchasing owns the PO, accepted receipt quantities, and physical return history.
- Accounts Payable owns the Vendor Bill and Vendor credit.
- `VendorSourceMapping(source_system="purchasing")` is the explicit bridge between operational and Accounting Vendor identities.
- Bill lines reference PO-line and optional receipt-line identities. Unknown, foreign, or missing identities fail into explicit exceptions.
- Exact quantity, unit-cost, currency, and mapped-Vendor evidence produces `matched / eligible` admission.
- Partial, missing, overbilled, returned-without-credit, Vendor, item, price, quantity, or currency evidence produces a review or blocked state. No tolerance is inferred.
- AP approval of a PO-backed bill requires an eligible active match whose full
  source-evidence digest remains current. Receipt, return, and linked Vendor
  credit evidence participate alongside PO and bill versions.

## Review controls

`COMPANY_ACCOUNTS_PAYABLE_MATCH_REVIEW` is distinct from read access and bill approval. Exception resolution is immutable and idempotent. The original evaluator cannot accept their own variance. Hold, reject, wait, credit-request, return, and manual-review dispositions remain non-posting operational evidence.

## Determinism and concurrency

Evaluation uses a Company-and-bill advisory transaction lock, stable idempotency
identities, row/version locks, and canonical evidence digests. One active match
authority exists per Vendor Bill. When receipt, return, credit, PO, or bill
evidence changes, reevaluation appends the next immutable sequence and marks the
prior evaluation superseded; historical lines and exceptions are retained.
Concurrent equivalent evaluation recovers the same active authority, and
contradictory evidence fails closed. Resolution commands have their own
Company-scoped idempotency identity and cannot mutate a superseded evaluation.

## Domain boundaries

Evaluation and review emit only safe procurement events. They create no
Inventory movement, AP subledger liability, Journal, payment, refund, or
Economics fact. A physical return does not fabricate a Vendor credit; a bill
that still includes returned quantity remains `return_pending_credit`. Arrival
of an explicitly return-linked AP credit supersedes stale admission but remains
`requires_review` until authorized review because tax, freight, and valuation
policy are not inferred. Cost is evidence only—no valuation method or Company
tolerance policy is selected.

## Vendor operational evidence

The read-only Vendor performance projection is definition-versioned and evaluated at an explicit cutoff over the caller's authorized Company/Branch scope. It reports attributable ordered, accepted, returned, net-accepted, fulfillment-ratio, completed lead-time sample, discrepancy, and matched price-variance evidence. Each Vendor row and report has a deterministic evidence digest. It produces no rating, financial impact, preferred-Vendor policy, or autonomous selection.
