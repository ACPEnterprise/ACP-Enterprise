# Common residential plumbing stock seed

Owner source: `pricebook_materials_template (1).numbers`  
SHA-256: `c9707e9abfc40a46be2ab0d234d7149857b5e7d9605a6aa747e152bb094c0712`

The source was inspected read-only with `numbers-parser` 4.16.3. It contains one sheet, one table, 362 rows including the header, and 19 columns. There are 361 source material rows. Rows 43 and 64 repeat the same Hughes part number (`828627`), description, and cost. The first is proposed and row 64 is held as duplicate source identity, producing 360 proposed ACP materials and one held row.

The importer is deliberately separate from Price Book. It creates active canonical Inventory items, certified vendor cross-references, append-only vendor purchase-cost evidence, and an append-only admission ledger. It creates no InventoryQuantity, StockMovement, PriceBookComponent, selling price, or service mapping.

Run a read-only inspection:

```console
python scripts/admit_common_stock_seed.py '/protected/input/pricebook_materials_template (1).numbers'
```

Admission requires an explicit Company and actor and must be run only after the migration is integrated:

```console
python scripts/admit_common_stock_seed.py '/protected/input/pricebook_materials_template (1).numbers' \
  --admit --company-id COMPANY_UUID --actor-user-id OWNER_USER_UUID
```

The admission records `opening_inventory_state=not_historically_reconstructed` and intentionally creates no opening quantities. The vendor cost basis is purchase cost before delivery/shipping and purchase-side sales tax. Planning cost remains an unactivated candidate (`highest_current_qualified_vendor_purchase_cost`) pending canonical Company policy and explicit owner approval.

Company users with `COMPANY_INVENTORY_MANAGE` can use **Inventory → Common stock seed catalog** as the normal operator path. Preview parses the workbook without persistence and displays its digest, proposed count, and held rows. Admission requires a second explicit action, resubmits the same workbook, and fails if its digest differs from the preview. The admission, audit record, and past-tense Business Event commit atomically. Read-only users cannot access either endpoint or see the controls.
