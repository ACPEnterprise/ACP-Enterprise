# PRICEBOOK.ALLCOUNTY.BUILD.1 — protected integration packet

## Scope

Non-production native Price Book operational home plus deterministic,
non-activating All County candidate derivation from owner evidence. No owner
original, Preview environment, Production environment, operational customer,
Job, invoice, payment, accounting posting, Inventory ledger or active price is
mutated.

## Authority and artifacts

- Base: `428dcbddd7d072b5b8d9edff489efcd4373960b5`.
- Final reconciled protected authority: `fd2af4057a8dc1ba14777e3c052dd6ed39656404`.
- Branch: `work/pricebook-allcounty-build-1`.
- Machine configuration: `all-county-build-1.configuration.json`.
- Owner-readable packet: `PRICEBOOK.ALLCOUNTY.BUILD.1.md`.
- Consolidated decisions: `PRICEBOOK.ALLCOUNTY.BUILD.1.owner-decisions.md`.
- Deterministic builder: `scripts/pricebook_allcounty_build.py`.
- Source gates: resolved; all seven requested artifacts are digest-bound.
- Vendor materials: 361 candidates / 360 unique identities / one exact
  duplicated part number; no Inventory mutation.
- Water Heater: 39 existing services reconciled; no duplicate services created;
  script examples remain non-authoritative review evidence.

## Integration controls

Enterprise owns protected integration and deployment. Before integration,
re-run the deterministic builder against the digest-bound sources, inspect the
packet diff, run affected backend/frontend qualification, prove a fresh
zero-to-head PostgreSQL migration and drift-free single head, and confirm the
branch reconciles current protected authority. Real candidate activation is a
separate owner authorization and is not included in this packet.

## Successor qualification evidence

- Deterministic source replay: byte-for-byte match.
- Packet/backend non-database Price Book tests: 5 passed.
- PostgreSQL Price Book service tests: 14 reached fixture setup and were
  environment-gated because the configured Docker hostname `postgres` is not
  resolvable on this host; no product assertion failed.
- New Python source: Ruff clean, MyPy clean, Python 3.12 compilation clean.
- Frontend Price Book route: 6 tests passed; ESLint clean; TypeScript and Vite
  Production-mode build passed.
- Repository diff check and protected-data scan: clean.
- No schema/model change is introduced by this successor; the inherited Alembic
  graph has one head, `m9n7q05f2s8t`. Fresh database qualification remains an
  Enterprise integration gate.
