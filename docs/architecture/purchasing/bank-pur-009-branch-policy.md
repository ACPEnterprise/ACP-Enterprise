# BANK.PUR.009 — Branch purchasing policy configuration

PUR.9 makes branch/item replenishment targets durable Purchasing evidence. Each
configuration is Company/Branch scoped, explicitly attributed, version checked,
idempotent, and backed by immutable revision evidence and a canonical digest.

The configured target is an operational Purchasing input. It does not select a
Vendor, set a price, create or approve a Purchase Order, receive Inventory, create
AP liability, post Accounting, make a payment, or create Economics truth. Missing
or unauthorized Company/Branch/item evidence fails closed. Updating or deactivating
a policy creates a new revision; prior evidence is never rewritten.

`COMPANY_PURCHASING_READ` can inspect policy evidence.
`COMPANY_PURCHASING_MANAGE` is required to configure it. Optimistic version checks
prevent stale updates and Purchasing command receipts provide deterministic replay.
