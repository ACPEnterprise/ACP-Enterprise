# All County Price Book review readiness

Milestone: `PRICEBOOK.ALLCOUNTY.REVIEW.READINESS.1`

This candidate adds a management-only review queue and a deterministic reference
review packet. It does not activate a Price Book version, import reference rows,
or change Estimate selection rules.

## Reference candidate accounting

Run:

```bash
python scripts/pricebook_allcounty_review.py \
  docs/architecture/price-book/all-county-build-1.configuration.json \
  --output /tmp/all-county-review.json
```

For the authoritative build packet, the deterministic result is:

- service candidates: 218
- `READY_FOR_REVIEW`: 218
- `READY_FOR_ACTIVATION`: 0
- packet digest: `2c92dec7bb97b8920d708fedda7121850e319f8d19bb4c52ca202cd4752c2137`
- activation status: `NOT_ACTIVATED` for every row

All 218 retain four explicit owner inputs before activation readiness: native
Branch, effective date, tax classification, and material evidence. A missing
value is never converted to zero. Source identity, code/name, descriptions,
category evidence, proposed standard price, and labor evidence remain visible in
the packet.

The duplicate unresolved vendor part identity `vendor-unresolved:828627`
preserves source rows 43 and 64 as `CONFLICTING`. The decision template supports
only `KEEP_BOTH`, `SELECT_ROW`, or `RETURN_TO_SOURCE_OWNER`, with actor, timestamp,
reason, and original source evidence. No choice merges, discards, imports, or
activates either row.

## Native management workflow

`GET /api/v1/price-book/review-queue` derives draft readiness using current
native Category, Branch, tax, component, source-audit, and management-review
evidence. Operators can search and filter by category, Branch, candidate state,
or activation readiness. Normal UI labels use code/name and business labels;
record identifiers remain transport-only.

Bulk draft input now carries `source_identity` separately from the request-only
`client_ref`. A missing source identity remains explicitly incomplete; a source
identity already bound in native audit lineage, or repeated in the same batch,
is rejected as a duplicate. Browser-generated correlation IDs therefore cannot
be mistaken for provenance.

`POST /api/v1/price-book/review-queue/bulk` atomically applies only:

- category;
- Branch;
- tax classification;
- effective date; or
- individual-review marking.

The command locks each draft, checks item and version concurrency, validates
Company/Branch ownership and active reference data, increments versions, and
writes an audit entry. Its schema has no price, cost, lifecycle, or activation
field.

`POST /api/v1/price-book/review-queue/{version_id}/decision` records an individual
management decision in the existing Price Book audit history. `REVIEW_COMPLETE`
fails before mutation unless all mechanically mandatory evidence is present.
The resulting `READY_FOR_ACTIVATION` classification is evidence only; the
existing separately authorized, per-version activation action is still required.

The review queue requires `COMPANY_PRICE_BOOK_MANAGE`, so internal cost totals
remain unavailable to ordinary Price Book readers. Existing Estimate catalog
resolution remains unchanged: only active, currently effective, non-expired
versions are selectable and the immutable Estimate snapshot contract remains in
force.

## Enterprise qualification and handoff

No schema change is introduced. Protected PostgreSQL qualification must exercise
atomic bulk metadata edits, stale-version rejection, invalid Branch/category/tax
rejection, decision history, incomplete-review rejection, and successful review
completion. Existing Price Book lifecycle, authorization, Estimate integration,
and immutable snapshot suites remain required.

No activation or live-data mutation was performed in this lane.
