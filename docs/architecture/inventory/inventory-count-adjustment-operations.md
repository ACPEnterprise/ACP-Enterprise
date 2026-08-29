# Inventory count and adjustment operations

This capability exposes the existing native Inventory movement authority for
evidenced quantity corrections and physical counts. It does not create a
second quantity ledger or infer a financial valuation.

## Authority boundaries

- `COMPANY_INVENTORY_COUNT` starts a Company/Branch/location-scoped count and
  records immutable observations.
- `COMPANY_INVENTORY_ADJUST` posts an explicit signed correction with a bounded
  reason and operator note. It is also required to approve completion of a
  count using an expected session version. Completion posts each observed
  variance through that same native adjustment and movement authority.
- Counters therefore cannot apply their own observations unless they also hold
  the separately assigned adjustment authority. Expected, observed, variance,
  adjustment, and movement evidence remain inspectable.
- Transfer, receipt, return, reservation, AP, Accounting, Payments, and
  Economics authorities remain independent.

## Determinism and audit

Identical command replay recovers existing authority and emits no duplicate
Business Event. Contradictory reuse fails closed. Completion checks the current
count version, and count entries capture the location quantity observed at the
time of the count. Events contain scoped identities and quantities, not
financial valuation or protected source payloads.

## Operator workflow

Read-authorized users can inspect completed and open count evidence. Adjustment
and count controls are independently permission-gated. The operator selects a
Branch, item, and location explicitly; the frontend never owns the business
decision and always reconciles mutations back to server state.

No schema migration is introduced. The durable adjustment, movement,
cycle-count session, and cycle-count entry models were already part of the
authoritative Inventory schema.
