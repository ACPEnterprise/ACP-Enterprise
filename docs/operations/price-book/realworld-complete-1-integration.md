# PRICEBOOK.REALWORLD.COMPLETE.1 integration and acceptance

## Authority and scope

- Starting protected authority: `4be32635f4c9d8b684c8d97521f6e0092f666661`.
- Candidate branch: `work/pricebook-realworld-complete-1`.
- This candidate composes the prior All County Build.1 and Activation Readiness evidence onto the protected lineage. It does not activate a real price.
- Candidate configuration remains 218 services, 16 categories, 208 formula-derived prices, 10 explicit workbook overrides, 218 configured labor estimates, and 361 vendor-material candidates.
- Canonical `pricebook_materials_template.numbers` source remains pinned to SHA-256 `487afc22f1a09eee86647ea29272e95d71a347070af113e317b90f0296b9052c`. The `c9707e...` representation is not substituted for that source.

## Read-only prerequisite sweep

The protected foundation already supplied Company/Branch-scoped categories, tax classifications, service items, draft/active/superseded price versions, labor and material components, effective dates, currencies, option groups/options, explicit transactional activation, optimistic draft edits, lifecycle transitions, historical resolution, immutable commercial snapshots, audit entries, Business Events, and separate READ/MANAGE/ACTIVATE permissions. Estimates consume immutable Price Book snapshots; invoices retain the snapshot identity through their Estimate lineage.

The sweep found these operating gaps:

1. The catalog API was unbounded and did not support server-side name/code/description search, category/status/version filters, or pagination.
2. Categories and service identities could be created but not maintained through guarded update contracts.
3. Planned costs had labor/material types but no explicit other-direct-cost type or truthful aggregate readiness.
4. Managers could not see cost completeness and ordinary readers needed an explicit guarantee that unit costs were omitted.
5. Bulk proposals could be recorded and approved but could not create exact, replay-safe successor drafts.
6. Estimate entry required an engineer-facing commercial snapshot UUID instead of allowing selection of an active service and option.
7. The owner UI did not show effective/version comparison or expose the bounded bulk-adjustment lifecycle.

## Integration order

1. Merge this candidate onto current protected authority.
2. Confirm a single Alembic head. Candidate head is `n0p8q16g3t9u`; reconcile its `down_revision` if protected authority has advanced.
3. Apply the migration in Preview. It adds Price Book review/adjustment persistence, successor-draft materialization evidence, and the `other_direct` component constraint; it does not load or activate prices.
4. Deploy backend and frontend together because the catalog response and Estimate Price Book selector are coordinated.
5. Run the qualification and owner acceptance below.

Rollback before owner activation is application rollback plus Alembic downgrade to the pre-candidate protected head. If any Preview-only successor drafts were made, retain their audit evidence and archive them through the product instead of deleting history.

## Qualification commands

From `backend/`, against supported PostgreSQL:

```bash
alembic heads
alembic upgrade head
alembic current
pytest tests/price_book tests/estimates tests/invoices tests/jobs -q
ruff check app tests alembic
mypy app
python -m compileall -q app tests
```

Run the repository drift check and credential/protected-data scan used by the protected integration pipeline. From `frontend/`:

```bash
npm ci
npm run lint
npm run test:run
npm run build
```

## Preview owner acceptance script

Use an authorized synthetic/Preview Company context until the owner explicitly approves real All County activation.

1. Sign in as a Price Book READ+MANAGE+ACTIVATE operator and open Price Book.
2. Search for an existing service by customer name, then by service code; filter its category and lifecycle state.
3. Create a category and create a service item in it.
4. Edit the service's customer-facing identity and save it; confirm the version-conflict recovery path by attempting a stale update in a separate session.
5. Create a draft price version with selling price, effective date, tax classification, labor, material, and (where applicable) other direct cost.
6. Add or select an option group and option, and verify the customer-facing description contains no internal costs.
7. Compare the draft price and effective date with the active revision. Confirm missing cost evidence says `INSUFFICIENT_COST_EVIDENCE` and does not invent margin.
8. Activate the draft intentionally. Confirm the prior active revision is historical/superseded and audit history names the action.
9. Open Estimates, supply Branch and Customer, select the active Price Book service and option, set quantity, and create the Estimate. Do not paste a snapshot identifier.
10. Confirm the Estimate line has the selected description, option, quantity, price, tax metadata, Price Book version identity, and deterministic total.
11. Return to Price Book, create and activate another successor price.
12. Reopen the first Estimate and its downstream Job/Invoice view. Confirm the first sold price and snapshot identity did not change.
13. Filter Price Book to a bounded category or explicit search set. Enter a percentage or fixed adjustment and an effective date; save the exact preview.
14. Record the affected count and before/after values. Cancel the preview and confirm no draft or active price changed.
15. Repeat, approve the exact preview, and create successor drafts. Confirm no price became active.
16. Review the created drafts, then activate only the explicitly authorized synthetic group. Confirm replay does not create duplicate drafts or activations.
17. Review Price Book audit/history for the source proposal, approval identity, materialization, successor lineage, and activation.
18. Sign in as a READ-only operator. Confirm browsing and Estimate selection work, while create/edit/activate/bulk controls and all unit/direct costs are unavailable.

## Legacy/import boundary

HCP remains reference evidence only. Existing evidence must be classified per item as `SAFE_IMPORT_CANDIDATE`, `OWNER_REVIEW_REQUIRED`, `DUPLICATE`, `LEGACY_ONLY`, `SOURCE_MISSING`, or `NOT_APPLICABLE`; no name-only merge or automatic promotion is permitted. The retained provider-neutral candidate contract binds source identity/item ID/version or as-of date, proposed category/service, duplicate and mapping states, review state, native/imported disposition, unresolved fields, and final disposition. This candidate does not create a broad consulting workflow.

## Remaining closure gates

Technical candidate completion is not real-world closure. Enterprise must integrate it, deploy Preview, migrate and verify Preview health, and the owner must pass the script with an authorized real All County candidate item. The 39 source-conflicting services, tax-treatment decisions, membership authority, owner price approval, and the 194 incomplete material mappings retain their existing review classifications. Cost incompleteness does not alone block commercially complete non-member service use. Production remains untouched.
