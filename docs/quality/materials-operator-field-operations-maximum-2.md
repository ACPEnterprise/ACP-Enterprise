# Materials operator and field operations maximum 2

Starting protected authority: `15287f82f3c5a40a97baf2da4505beb24a7b58c3`.

## Delivered boundaries

- The isolated Inventory regression harness explicitly registers the integrated
  Customer, Scheduling and Job mapper graph. It changes no product behavior and
  restores full PostgreSQL-backed Inventory regression coverage.
- Inventory overview includes recoverable allocation and immutable material
  issue/reversal history.
- An Inventory reserver may issue a full or partial allocation only when its
  reservation identifies an authoritative Company/Branch Job.
- Issue replay is Company-scoped and allocation-unique. It creates physical
  stock movement and actual Job-consumption evidence.
- Unused material return is an immutable compensating reversal linked to the
  original issue. It restores stock without deleting or rewriting history.
- Operators select a readable Job by business number and Customer when creating
  Job reservations; the normal UI no longer asks them to paste a Job UUID.
- Actual material cost history comes only from accepted PO receipt lines. It
  retains vendor, PO/line, receipt/line, date, quantity/unit, cost, currency and
  source reference.
- Valuation readiness identifies unvalued stock, currency conflicts and the
  outstanding valuation-method policy. Receipt cost is never described as an
  Accounting valuation or posting.

## Preserved authority

- Warehouse, vehicle, staging, transit and quarantine locations remain the
  canonical stock-location model.
- Transfers retain source/destination, actor/time and negative-stock protection.
- Reservations, allocations, issues and reversals remain separate facts.
- Existing Purchasing requisition, approval, PO, change, receipt, discrepancy,
  vendor return, replenishment-review and document-custody authority is reused.
- Sold Price Book and Estimate snapshots remain immutable and are not edited by
  Inventory operations.
- No autonomous purchasing, Accounting posting, Mobile UI, Dispatch assignment,
  Beacon lifecycle or Luminary calculation is introduced.

## Enterprise integration order

1. Integrate PR #340 before or reconcile it with this branch; this branch does
   not duplicate its material item-master or Job-material projection changes.
2. Integrate this branch after its current protected-authority merge.
3. Run PostgreSQL zero-to-head and the complete Inventory suite.
4. Run Inventory route/API tests, ESLint, TypeScript and production build.
5. In Preview, use an authorized Inventory operator and sanctioned records to
   run the acceptance below. Do not use Production purchasing.

## Sanctioned real acceptance

1. Find or create the real material item through the integrated item-master UI.
2. Confirm the exact SKU; do not use description similarity.
3. Select the real warehouse or truck location and verify current on-hand.
4. Select the real Job by Job number and Customer and request the required quantity.
5. Allocate all or an explicitly partial available quantity and verify available
   stock decreases while on-hand does not.
6. Issue that allocation to the Job and verify on-hand and reserved quantities,
   immutable issue evidence, Job identity and consumed quantity.
7. Verify actual receipt-cost evidence where a source PO receipt exists and
   confirm valuation policy remains visibly required.
8. Return an unused issue and verify linked reversal evidence and stock restoration.
9. Use existing sanctioned Purchasing workflows for a requisition, PO and
   partial/full receipt only when the owner authorizes the real purchase.
10. Confirm no autonomous PO, Accounting posting, Price Book rewrite or
    unapproved substitution occurred.

## Explicit remaining gates

- Vendor catalog/SKU and manufacturer identity require a new certified
  vendor-product authority; PO history alone is not an equivalence decision.
- Preferred-vendor selection requires explicit owner purchasing policy.
- FIFO, weighted-average, specific-identification or another valuation method
  requires accountant/owner approval.
- Optional and substitute-part rules require owner policy and exact part
  certification.
- Assignment-scoped technician material APIs should compose with PR #340 after
  its protected integration; Mobile UI remains outside OM2-B.
- Real All County acceptance requires sanctioned live item, Job, location and
  receipt evidence and cannot be replaced by synthetic fixtures.
