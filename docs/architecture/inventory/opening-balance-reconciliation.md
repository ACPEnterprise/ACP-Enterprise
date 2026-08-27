<!-- markdownlint-disable MD013 -->

# INV.OPENING.1 — Inventory opening-balance reconciliation

## Status and authority

`PLANNED / NOT STARTABLE`

On August 27, 2026, the owner explicitly separated historical/opening-balance
completeness from bounded operational `INV.2A`. This record preserves that future
boundary; it does not Start or implement reconciliation.

Until accepted evidence proves otherwise, opening-balance completeness is
`unknown / not-yet-reconciled`. Missing source evidence, an absent quantity row,
or no recorded movement must never be represented as a certified zero.

## Future objective

Reconcile an immutable, checksummed, owner-approved source snapshot to ACP's
Inventory movement and quantity evidence at a declared Company/Branch/location
cutoff. Every source row and variance must be accepted, rejected, or explicitly
dispositioned exactly once. Quantity completeness and any financial valuation
assertion remain separate controls.

## Dependencies and gates

- accepted authoritative source identity, custody, cutoff, checksums, units, and
  Company/Branch/location mapping;
- owner decision on completeness granularity and who may certify or revoke it;
- explicit migration/import contract, dry-run and rollback evidence;
- current Inventory and Accounting ownership review; and
- separate authorization for any TYPE C rehearsal, Preview, Production, import,
  cutover, or irreversible operation.

Unknown values may not be fabricated or coerced to zero. No real customer data,
source export, schema, migration, or runtime behavior is authorized by this file.

## Relationship to launch work

`INV.2A` may complete without this milestone. `PUR.1` may consume authoritative
operational Inventory identity and movement contracts without claiming historical
stock completeness. Any purchasing recommendation, financial reconciliation, or
cutover assertion that depends on complete opening quantities remains fail-closed
until this milestone is separately accepted.
