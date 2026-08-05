# Receiving and Cost Evidence

## Three distinct facts

Receiving crosses three authorities that must remain distinct:

1. Purchasing records what was ordered and physically received or rejected.
2. Inventory records the accepted physical quantity movement and its valuation
   evidence.
3. Accounting/QuickBooks records a vendor bill, liability, payment, and ledger
   consequences when accounting controls establish them.

Success in one does not imply success in another. The integration records pending,
completed, exception, and not-applicable state with stable idempotency identities.

## Receipt line evidence

Each receipt line references the immutable PO version and line; snapshots Vendor,
ordered/received units, quantities, currency, agreed cost and permitted ancillary
cost evidence; distinguishes accepted, rejected, damaged, and short quantities;
records receiver, times, source document evidence, discrepancy codes, and correction
chain; and optionally records returned Inventory movement identities.

Quantities and money are decimal. Currency is explicit. Item-specific unit conversion
is versioned and preserved. A receipt cannot silently change PO terms. Unknown final
cost remains unknown; zero is a measured value, not a missing-value default.

## Inventory posting contract

Purchasing submits Company, Branch, receipt/version/line idempotency identity,
Inventory item, destination location, accepted quantity/unit, occurrence time, and
cost-evidence envelope to Inventory. Inventory independently validates scope, units,
location, item lifecycle, duplicate posting, and movement rules. It returns an
immutable movement identity or controlled contradiction.

A retry returns the same logical result. A correction requests a linked compensating
movement. Purchasing cannot update the movement or balance directly. Partial posting
is line-visible and cannot make a whole receipt appear reconciled.

## Cost evidence and valuation boundary

Purchasing owns agreed and received procurement cost evidence. Inventory may consume
eligible unit/landed-cost facts to value movements under a separately approved
operational valuation policy. It preserves method label, source receipt line/version,
currency, quantity/unit, allocations, effective time, and confidence/completeness.

Inventory valuation is operational evidence, not a general ledger. Freight, tax,
discount, rebate, and landed-cost allocation rules are deferred until explicitly
approved. Later cost corrections create new valuation evidence or adjustments; they
never rewrite the original receipt or movement.

QuickBooks remains authoritative for AP liabilities, vendor bills/credits/payments,
account mapping, posting periods, journal consequences, and financial statements.
No receipt creates AP automatically. A future accounting handoff contains immutable
source identity/version and reconciliation status without granting QuickBooks write
authority over Purchasing or Inventory.

## Discrepancy and failure behavior

Overage, shortage, damage, substitution, unit mismatch, price variance, duplicate
delivery, unknown Inventory mapping, and closed-period accounting conflicts are
separate controlled classes. They are not collapsed into free text. Owner-visible
exceptions show responsible domain and next allowed action.

When Inventory posting fails, receipt truth remains and stock state is pending or
exception. When accounting handoff fails, receipt and stock remain unchanged. When
the external accounting outcome is unknown, blind retry is prohibited until lookup
or owner reconciliation establishes whether an external record exists.

## Business Economics inputs

Business Economics may consume ordered cost, received cost, price variance, receipt
quantity, waste/damage, Inventory issue-cost snapshots, and accounting-reconciled
cost as separately labeled facts. Every projection includes provenance, freshness,
currency, unit, confidence/completeness, and correction state. It must not select an
authoritative cost silently when sources disagree and cannot mutate any source.

## Deferred policy decisions

Three-way matching, landed-cost allocation, standard/average/FIFO valuation,
approval thresholds, tolerance bands, vendor returns/credits, tax treatment, and
QuickBooks bill transport are future owner-reviewed decisions. This contract
preserves evidence needed for them without choosing accounting behavior.
