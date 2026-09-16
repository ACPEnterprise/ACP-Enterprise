# Field Purchase Receipt Intelligence

## Authority and boundaries

This candidate starts from protected authority `4b21832cd7b97f0a16b1aaaf8b16cc083f4aef0e` and depends only on protected contracts. PRs #340 and #350 remain frozen and are not modified or copied.

A field purchase is receipt-backed evidence. It is not, by itself, an Inventory receipt, Job issue, Accounting expense, reimbursement, or payment fact. The product permanently retains three separate truths:

1. expected material from the sold Price Book/Estimate snapshot;
2. purchased material from protected receipt evidence;
3. actual consumption from an explicit Job issue.

## Runtime contract

Technician routes are assignment-scoped and require `COMPANY_JOB_EXECUTE`:

- create/finalize the canonical protected field artifact;
- `POST /api/v1/technician/jobs/{job_id}/field-purchases`;
- `POST /api/v1/technician/jobs/{job_id}/field-purchases/{purchase_id}/extractions`;
- `POST /api/v1/technician/jobs/{job_id}/field-purchases/{purchase_id}/dispositions`.

Office review uses `GET /api/v1/field-purchases/review` with Inventory read authority. Exact reusable vendor-code certification uses `POST /api/v1/field-purchases/vendor-mappings` with Purchasing manage authority.

The extraction boundary is provider-neutral. Current sanctioned methods are manual review, deterministic synthetic fixtures, or a future provider adapter. No provider is selected or contacted. Values retain confidence and source evidence; absent values stay absent.

Exact automatic item resolution requires an active, owner/operator-certified Company + vendor + vendor code mapping. Receipt descriptions never establish authority. Unknown lines remain `unmatched`; no Inventory item is created.

## Disposition and downstream composition

Quantities may split among `used_on_this_job`, `keep_on_truck`, `return_or_unused`, and `non_inventory`. The sum may not exceed the purchased quantity. Stock-affecting choices require an exact Inventory item. Truck retention additionally requires an active vehicle Inventory location in the same Company and Branch; otherwise it remains pending review.

With the protected Inventory wave present, exact matched and location-authorized
dispositions compose atomically into canonical `purchase_receipt` movements.
`used_on_this_job` additionally creates the canonical Job reservation,
allocation, and issue chain; `keep_on_truck` retains the received remainder at
the authorized vehicle location. Missing location authority remains held for
review. Exact command replay returns the original result without duplicating
movements, reservations, allocations, issues, versions, or events.

Non-inventory lines retain Job/source evidence only. Accounting classification, reimbursement, payment method, tax treatment, COGS, asset, and expense-account decisions remain outside this domain.

## Security and replay

- Receipt bytes remain in canonical protected field-artifact storage; this domain stores only the opaque artifact identity and digests.
- Responses contain no blob URL, storage reference, card data, or receipt body.
- Company, Branch, Job assignment, Employee identity, and authorization version are enforced.
- A protected artifact can back only one purchase.
- Command keys and extraction digests converge exact replay and reject conflicting reuse.
- Vendor mappings are versioned and must be explicitly superseded.
- No public URLs, OCR payload logs, provider secrets, or Accounting data are introduced.

## Beacon, Economics, Price Book, and Luminary handoffs

The review projection exposes deterministic blockers for incomplete extraction, unmatched lines, and missing truck location. Beacon may consume those facts but owns alert lifecycle.

Receipt line cost, exact item identity, confirmed disposition, receipt digest, Job identity, and later issue/reversal lineage form the Economics evidence contract. Economics/Luminary own interpretation; this domain does not calculate profitability, waste, technician performance, standard truck stock, or Price Book changes.

Price Book expected-material snapshots remain immutable and are not updated by receipt evidence.

## Real All County acceptance

Closure requires an authorized operator and assigned technician on a sanctioned real Job:

1. capture and finalize a real receipt through protected artifact custody;
2. create the field purchase and verify exact replay returns the same identity;
3. review vendor/date/total and provenance;
4. verify a certified code resolves exactly and an unknown code remains unmatched;
5. split one line between used-on-Job and keep-on-truck;
6. verify the truck location is authoritative;
7. after Inventory-wave reconciliation, verify receipt and Job issue movements plus Job/Economics evidence;
8. verify the receipt stays protected and auditable;
9. confirm no Inventory item, purchase order, Accounting posting, or purchase is created automatically.

Synthetic qualification proves engineering behavior but cannot satisfy owner acceptance.

## Enterprise integration

1. Integrate this candidate after normal review.
2. Apply Alembic revision `a2c4e6g8i175` (schema-only; no data rewrite).
3. Run the field purchase, field artifact, idempotency, Inventory, Purchasing, authorization, and migration-head suites.
4. Verify OpenAPI exposes the routes and protected artifact responses contain no storage reference.
5. Do not enable a real extraction provider.
6. When #340/#350 reach protected authority, reconcile confirmed disposition → canonical Inventory receipt/Job issue/reversal and attach their immutable IDs. Do not reinterpret historical confirmations.
7. Execute the real acceptance script only under separate sanctioned Preview authorization.

Rollback disables the routes and application artifact first, then downgrades the schema only if no retained field-purchase evidence exists. Never delete retained receipt evidence to force rollback.
