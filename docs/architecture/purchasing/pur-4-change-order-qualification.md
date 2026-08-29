# PUR.4 purchase-order change control qualification

PUR.4 treats an issued Purchase Order and its immutable issuance evidence as the
first effective revision. A requested change records its Company, Branch,
Purchase Order, base revision, canonical evidence digest, requester, proposed
operations, and reason. Approval uses a separate Purchasing approver, locks the
Purchase Order and change request, verifies the base revision, applies the
change atomically, and writes the next immutable effective snapshot.

The accepted lifecycle is deliberately compact: `requested` is the submitted
proposal, `rejected` is terminal without an effective revision, and `approved`
means approved **and atomically applied**. There is no interval in which an
approved change is waiting to be applied. This interpretation preserves
preparer/approver separation, exactly-once command receipts, stale-base
rejection, and immutable revision history without requiring another business
decision. A later workflow that separates approval and application would be a
new Purchasing milestone rather than an implicit PUR.4 behavior change.

Field controls are fail closed:

- Quantity may change only at or above cumulative accepted receiving.
- A line without accepted receiving may be explicitly canceled; it is never
  deleted.
- Unit cost may change before accepted receiving.
- Any accepted receiving permanently closes unit-cost mutation, including when
  all received units were later returned. The service returns
  `POST_RECEIPT_PRICE_CHANGE_POLICY_REQUIRED`; neither reconciliation evidence
  nor a downstream flag substitutes for an approved valuation/prospective
  policy.
- Expected date and complete new-line proposals remain eligible Purchasing
  facts. Vendor, currency, item identity, receipts, discrepancies, returns, and
  downstream financial facts are not rewritten.

Purchasing change orders produce only Purchasing revisions and Business Events.
They do not mutate Inventory, StockMovement, material issues, AP, Accounting,
Payments, job-material consumption, or Business Economics policy truth.
