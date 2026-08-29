# Procurement three-way matching authority

The native procurement match compares immutable Purchasing and Accounts Payable evidence. It does not rewrite a Purchase Order, receipt, return, Vendor Bill, Inventory movement, or Accounting fact.

## Authority and admission

- Purchasing owns the PO, accepted receipt quantities, and physical return history.
- Accounts Payable owns the Vendor Bill and Vendor credit.
- `VendorSourceMapping(source_system="purchasing")` is the explicit bridge between operational and Accounting Vendor identities.
- Bill lines reference PO-line and optional receipt-line identities. Unknown, foreign, or missing identities fail into explicit exceptions.
- Exact quantity, unit-cost, currency, and mapped-Vendor evidence produces `matched / eligible` admission.
- Partial, missing, overbilled, returned-without-credit, Vendor, item, price, quantity, or currency evidence produces a review or blocked state. No tolerance is inferred.
- AP approval of a PO-backed bill requires an eligible match whose PO and bill versions remain current.

## Review controls

`COMPANY_ACCOUNTS_PAYABLE_MATCH_REVIEW` is distinct from read access and bill approval. Exception resolution is immutable and idempotent. The original evaluator cannot accept their own variance. Hold, reject, wait, credit-request, return, and manual-review dispositions remain non-posting operational evidence.

## Determinism and concurrency

Evaluation uses a Company-and-bill advisory transaction lock, stable idempotency identities, row/version locks, canonical evidence digests, and one match authority per Vendor Bill. Concurrent equivalent evaluation recovers the same authority; contradictory evidence fails closed. Resolution commands have their own Company-scoped idempotency identity.

## Domain boundaries

Evaluation and review emit only safe procurement events. They create no Inventory movement, AP subledger liability, Journal, payment, refund, or Economics fact. A physical return does not fabricate a Vendor credit; its absence remains `return_pending_credit`. Cost is evidence only—no valuation method or Company tolerance policy is selected.
