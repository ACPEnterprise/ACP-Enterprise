# PRICEBOOK.ALLCOUNTY.MIGRATION.RECONCILIATION.1

## Authority and lineage

- Protected authority: `7d12ffeec1ff6de2f0a7dcfee8ba8e899bf71e6c`.
- Original Price Book branch head: `352ebb338503f4581f9cc2de9e743eac3b4f2221`.
- Old graph: Price Book `n0p8q16g3t9u` and protected communications
  `n0p8r16g3t9u` were sibling heads after `m9n7q05f2s8t`.
- Reconciled graph: `m9n7q05f2s8t` → protected communications
  `n0p8r16g3t9u` → Price Book `n0p8q16g3t9u`.
- Exactly one candidate head: `n0p8q16g3t9u`.

The Price Book revision was not deployed or protected, so its parent was
forward-reconciled onto the current protected head. The protected communications
revision and its history were not modified. The revisions own disjoint tables.

## Canonical replay

Canonical source:
`~/Desktop/ACPL docs/pricebook_materials_template.numbers`

- Registered and observed SHA-256:
  `487afcbbce7584471c691507616c2f87464ee2959105b1b03bfe41eee03e92a9`.
- Committed BUILD.1 packet SHA-256:
  `09b9b3f132b38c5882ea2b338860f68df5fe6efaec8ec8f69a9853ab2ccac08c`.
- Fresh replay packet SHA-256:
  `09b9b3f132b38c5882ea2b338860f68df5fe6efaec8ec8f69a9853ab2ccac08c`.
- Byte-for-byte replay: `PASS`.

Reproduction command:

```bash
PYTHONPATH=/tmp/pricebook-backend312:backend /usr/local/bin/python3.12 \
  scripts/pricebook_allcounty_build.py \
  --source-dir "$HOME/Desktop/ACPL docs" \
  --ingested-at '2026-09-02T16:33:46-04:00' \
  --output /tmp/all-county-build-1.canonical-replay.json
shasum -a 256 \
  "$HOME/Desktop/ACPL docs/pricebook_materials_template.numbers" \
  docs/architecture/price-book/all-county-build-1.configuration.json \
  /tmp/all-county-build-1.canonical-replay.json
cmp docs/architecture/price-book/all-county-build-1.configuration.json \
  /tmp/all-county-build-1.canonical-replay.json
```

Do not qualify BUILD.1 from the distinct `c9707e…` Downloads representation,
even though its normalized material projection is equivalent. A new digest with
different normalized evidence must become a successor source, never rewritten
BUILD.1 history.

## Preserved configuration truth

- Services: 218; categories: 16; vendor-material candidates: 361.
- Workbook-formula prices: 208; explicit owner overrides: 10.
- Labor assumptions: 218 `CONFIGURED_ESTIMATE` values.
- Material mapping incomplete: 194 services.
- Accountant tax review: 218 services, grouped into 16 reusable decision groups.
- Active real prices: 0.
- Owner work-hour, selling-rate, discount, after-hours, membership, category,
  Water Heater, and activation decisions remain candidate policy gates. No value
  was invented or changed during reconciliation.

## Integration order

Enterprise should integrate the Build 1 history and activation-readiness history
through this branch as one ancestry chain. Apply the protected communications
revision before the Price Book review/proposal revision. Require fresh
zero-to-head, protected-head-to-candidate-head, current=head, one-head, drift,
downgrade/re-upgrade, affected backend/frontend, deterministic replay, static,
and protected-data checks before protected integration.

No real Price Book activation, repricing, Production deployment, accounting
posting, or mutation of operational Customers, Jobs, Estimates, or Invoices is
authorized by this packet.

## Qualification result

- PostgreSQL 16 fresh zero-to-head: pass.
- Protected `n0p8r16g3t9u` to Price Book `n0p8q16g3t9u`: pass.
- Current=head, exactly one head, and Alembic drift: pass.
- Price Book migration downgrade/re-upgrade: pass.
- Affected Price Book, Estimates, Service Agreements, Inventory, Economics,
  events/audit, Communications, Invoicing, authorization, and idempotency:
  433 passed on a fresh database.
- Frontend: 108 files and 366 tests passed; ESLint, TypeScript, and production
  build passed.
- Focused Ruff, MyPy, Python compilation, deterministic replay,
  `git diff --check`, and changed-file protected-data scan: pass.
