# PUR.5 terminal disposition qualification

PUR.5 records immutable, Company/Branch-scoped Purchasing evidence when a
Purchase Order is fully satisfied, canceled before receiving, or closed with a
partially received remainder canceled. Terminal disposition locks the Purchase
Order, verifies its current version and effective revision, rejects unresolved
receiving discrepancies, pending changes, and active returns, and preserves an
idempotent command receipt and exactly-once Purchasing Business Event.

Each line's terminal evidence reconciles its effective ordered obligation as:

`effective ordered = accepted received + canceled or unfulfilled remainder`

The canceled remainder includes both the open remainder canceled by the
terminal command and quantities already canceled by an accepted PUR.4 change
order. PUR.5 consumes that prior cancellation state without modifying the
change order, revision snapshot, receipt, discrepancy, or return history.
Operational outstanding quantity reaching zero because a line was canceled is
not satisfaction: `fully_satisfied` requires no open or previously canceled
quantity on any line.

Accepted receiving remains historical receiving even after a Purchase Return.
Returns remain separate evidence and active returns block terminal disposition;
PUR.5 does not invent return-adjusted financial or fulfillment semantics.

Terminal disposition is Purchasing truth only. It creates no Inventory item or
movement, Material Issue, AP vendor or bill, Accounting journal, payment or
refund, or Business Economics fact. PUR.4's
`POST_RECEIPT_PRICE_CHANGE_POLICY_REQUIRED` boundary remains authoritative.
