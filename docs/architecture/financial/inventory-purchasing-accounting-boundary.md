# Inventory, Purchasing, and Accounting Boundary

- **Status:** Proposed Version 1.0 authority contract
- **Accounting system of record:** QuickBooks

This contract extends the [Operational Financial Boundary](operational-financial-boundary.md)
and [QuickBooks Controlled Handoff](quickbooks-handoff.md) without creating ledger or
accounts-payable behavior.

## Authority matrix

| Fact or decision | Authoritative owner |
| --- | --- |
| Customer-facing service/item price and descriptive expected components | Price Book |
| Job material requirements and actual consumption attribution | Operations-owned Jobs |
| Physical item identity, custody, quantity, movement, reservation, and valuation evidence | Inventory |
| Operational Vendor, PO, receipt, and procurement lifecycle | Purchasing |
| Vendor bills/credits, AP liability/payment, accounts, journal consequences, close, statements | QuickBooks/accounting |
| Provenance-aware profitability and cost projections | Business Economics within Analytics |

Ownership applies to tables, validation, lifecycle, corrections, and transactional
events. Cross-domain references are identifiers or immutable snapshots. No module
reads another module's private tables as its integration contract, and no module
writes them under any circumstance.

## End-to-end evidence flow

```text
Price Book expected component ──snapshot/reference──► Job requirement
Job actual use ──owned event/API──► Inventory issue (optional in Version 1.0)
Inventory reorder signal ──demand input──► Purchasing PO decision
Purchasing receipt ──owned command──► Inventory receipt movement
Purchasing + Inventory evidence ──controlled handoff──► Accounting/QuickBooks
All authoritative facts ──versioned projections/events──► Business Economics
```

Each arrow may be pending, rejected, or reconciled independently. It does not confer
ownership or imply the downstream action occurred.

The implemented PRICEBOOK.1 component provides descriptive identity, expected
decimal quantity, optional internal unit cost, and ordering position. It does not
currently provide a unit-of-measure field or Inventory item reference. Those are
future Price Book extension points; until approved and implemented, Jobs records
operational units and optional Inventory references under Operations ownership.

## Inventory valuation versus accounting

Inventory may retain operational unit-cost and valuation-method evidence so stock
movements and Job issues can be measured. Such evidence is a subledger-like
operational fact only; this milestone does not establish a perpetual inventory
subledger, cost-of-goods-sold policy, chart of accounts, posting periods, journal
entries, or financial-statement balances.

QuickBooks owns accounting classification, AP, vendor bills and credits, payment,
ledger postings, reconciliation, close, and statements. ACP export/reconciliation
records do not claim those consequences occurred until QuickBooks evidence confirms
them. QuickBooks cannot rewrite PO, receipt, movement, or Job facts; corrections
originate as append-only operations in the owning ACP domain and are handed off.

## Business Economics boundary

Business Economics consumes immutable, tenant-scoped facts such as:

- expected Price Book material composition and internal expected cost;
- Job required versus consumed quantities, returns, waste, and substitutions;
- Inventory issue quantity, cost snapshot, adjustments, and completeness;
- PO agreed cost, receipt cost, quantity/price variance, and discrepancies;
- reconciled accounting cost facts when available.

It labels source, version, occurrence time, currency/unit, freshness, confidence,
and reconciliation state. Missing cost is unavailable rather than zero. Conflicting
facts remain visible. Business Economics cannot change customer price, Job use,
stock, Vendor/PO/receipt, AP, or accounting records and cannot automatically recommend
or place orders under this milestone.

## Collision and integrity risks

- **Price Book:** a descriptive component or expected internal cost is not a stock
  item, movement, received cost, or customer charge adjustment.
- **Jobs:** required quantity is not reservation; consumption is not proof of an
  Inventory issue; Inventory correction cannot rewrite field evidence.
- **Invoicing:** used or received material does not create an Invoice line or alter
  an issued Invoice. Commercial scope remains authoritative.
- **Purchasing:** a reorder signal is not a PO; a receipt is not stock or AP until
  each owner records its fact.
- **Accounting:** operational valuation is not ledger truth. No domain invents a
  journal entry, bill, liability, payment, or account mapping.

Shared UUID/code values never imply shared identity. Unit and currency mismatches,
duplicate delivery, partial failure, unknown external outcome, cross-Company access,
and event reordering fail closed or become explicit reconciliation exceptions.

## Migration and compatibility

Existing imported Price Book components, material text, financial rows, vendor IDs,
and QuickBooks mappings remain provenance-bearing historical evidence. Additive
migrations must not reinterpret them as operational Inventory, Purchasing, AP, or
approval facts. Adoption requires explicit mapping, completeness assessment, and
immutable source links. Every new aggregate is Company-owned and Branch-scoped where
operationally applicable; numeric quantities/money use declared decimal precision.

Business Events and permissions described by the Inventory and Purchasing briefs
are proposals. Their eventual catalog integration must be owned, collision-checked,
and migrated explicitly; documentation does not reserve a live code or event name.

## Version 1.0 and later releases

Version 1.0 may stop at Job-owned requirements and actual material-use capture with
optional description, Inventory reference, and cost provenance. Complete opening
balances, warehouses, vehicle stock, reservations, transfers, cycle counts,
replenishment, vendors, POs, receiving, valuation, and AP are not prerequisites
unless separate launch evidence makes them necessary.

Later milestones may add Inventory identity and movements, then Purchasing and
receiving, then controlled accounting handoff. Barcode scanning, serial/lot tracking,
bins, automated replenishment, advanced valuation, three-way matching, and direct
QuickBooks transport each require separate architecture and acceptance criteria.
QuickBooks replacement remains a later accounting program with independent controls.

## Unresolved owner decisions

Implementation must not choose these without owner review:

1. Which material-use fields are mandatory for Version 1.0 launch.
2. Whether any opening warehouse or truck balances are launch-critical.
3. Canonical unit catalog, fractional-quantity, and conversion tolerances.
4. Negative-stock, backorder, substitution, and reservation-allocation policy.
5. Inventory valuation method and treatment of freight, tax, discount, and rebate.
6. PO approval thresholds, receiving tolerances, and three-way matching.
7. Vendor master ownership when QuickBooks and ACP identities disagree.
8. AP/QuickBooks transport and reconciliation detail beyond the existing controlled
   handoff contract.
