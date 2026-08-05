# Inventory Item and Location Identity

## Identity boundary

An `InventoryItem` identifies a physical thing that may be counted, moved, reserved,
or costed. It is Company-owned and has a UUID, stable normalized stock code, name,
stocking unit, lifecycle, concurrency version, attribution, and durable timestamps.
Optional manufacturer part number, UPC/EAN, internal barcode aliases, serial policy,
lot policy, dimensions, and controlled classification are extension fields.

A Price Book service item is not an Inventory item. The implemented PRICEBOOK.1
material component carries its own identity, type, code, label, expected decimal
quantity, optional internal unit cost, and position. It does not currently carry a
unit-of-measure field or an Inventory item reference. Versioned unit-of-measure and
Inventory-item mapping fields are future extension points for composition; adding
them would not promise availability, reserve stock, or make Inventory change
customer price. Free text and coincident codes never establish identity.

Jobs may reference an Inventory item when known and must also snapshot sufficient
description and unit evidence for durable use history. Historical Job evidence
survives Inventory archival or mapping changes.

## Codes, lifecycle, and Company isolation

Stock codes are unique among non-archived items within a Company. Barcode aliases
are typed, normalized, temporally attributable, and unambiguous within the policy
scope. Identifiers and codes are never reused after historical movement. Lifecycle
is `draft`, `active`, `inactive`, or `archived`; inactive items cannot enter new
movements except controlled correction, return, or disposition workflows.

Every relationship uses Company-compatible keys or equivalent constraints. Cross-
Company component mappings, locations, movements, reservations, vendors, and receipt
lines fail at the repository and database boundaries.

## Unit-of-measure rules

Each item has one immutable stocking unit after its first movement. Quantities are
positive decimal values in commands, with direction determined by movement type.
Precision and scale are declared by unit class. Binary floating point is prohibited.

Purchasing or field units may differ only through an item-specific, versioned exact
conversion such as `1 case = 24 each`. A unit label alone is not a conversion.
Dimensional conversions require compatible unit classes. Fractional quantities are
allowed only when the item/unit policy permits them. Conversion rounding, residuals,
and effective time are explicit and cannot silently alter Job actual-use evidence.

## Location identity

An `InventoryLocation` has Company, UUID, stable code, name, type, optional Branch,
lifecycle, custody metadata, and optional reference to an externally owned entity.
Initial location types are:

- `warehouse` for a durable storage facility;
- `vehicle` for truck or vehicle custody;
- `staging` for controlled temporary allocation;
- `in_transit` for a transfer whose custody has not completed;
- `quarantine` for unavailable inspection/damage stock.

The Inventory domain owns the stock-location identity, not the building, Branch, or
vehicle aggregate. A vehicle location references a future Fleet identity; it does
not copy vehicle lifecycle authority. Deactivation prevents new ordinary movement
but preserves historical evidence and requires remaining stock disposition.

Bins may later be child locations with cycle-safe ancestry and one Company. Location
hierarchies cannot imply quantity twice: a balance is posted at one leaf custody
location, while parent totals are projections.

## Mapping and compatibility

External/source item identities and legacy codes use append-only mapping records
with provider, source scope, source ID, Inventory item/version, confidence, effective
period, and evidence. Ambiguous mappings fail closed. Merging identities requires a
reviewed successor mapping and never rewrites movements.

The design preserves barcode aliases, serial numbers, lots/expiration, multiple
warehouses, vehicle stock, and bins as separately constrained identities. Version
1.0 need not populate or operationalize any of them to capture Job materials used.
