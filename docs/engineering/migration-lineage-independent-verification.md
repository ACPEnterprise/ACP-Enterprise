# Migration lineage independent verification

`backend/scripts/verify_migration_lineage.py` independently parses every
Alembic revision, rebuilds its graph, and compares the result byte-for-byte at
the contract level with `docs/engineering/current-migration-lineage.json`.

The verifier fails closed when:

- the expected source checkpoint is not an ancestor, or its migration tree
  differs from the current migration tree;
- the stored report is stale or a revision changed after the report;
- the expected head differs from the sole computed head; or
- duplicate revisions, missing parents, cycles, multiple roots, split heads,
  or incomplete ordering make the graph not release-ready.

The current Laptop Master checkpoint can be verified without modifying a
database:

```console
python3 backend/scripts/verify_migration_lineage.py \
  --repo-root . \
  --evidence docs/engineering/current-migration-lineage.json \
  --expected-head x3y5z7a9c1e4 \
  --expected-source-sha e3ac2c0647f3afd6b6f9447bf68664032351980b
```

This graph check complements, and does not replace, an isolated PostgreSQL
upgrade rehearsal. It never rewrites a migration or connects to a protected
database.
