# PRICEBOOK.ALLCOUNTY.BUILD.1 — protected integration packet

## Scope

Non-production native Price Book operational home plus deterministic,
non-activating All County candidate derivation from owner evidence. No owner
original, Preview environment, Production environment, operational customer,
Job, invoice, payment, accounting posting, Inventory ledger or active price is
mutated.

## Authority and artifacts

- Base: `428dcbddd7d072b5b8d9edff489efcd4373960b5`.
- Branch: `work/pricebook-allcounty-build-1`.
- Machine configuration: `all-county-build-1.configuration.json`.
- Owner-readable packet: `PRICEBOOK.ALLCOUNTY.BUILD.1.md`.
- Consolidated decisions: `PRICEBOOK.ALLCOUNTY.BUILD.1.owner-decisions.md`.
- Deterministic builder: `scripts/pricebook_allcounty_build.py`.

## Integration controls

Enterprise owns protected integration and deployment. Before integration,
re-run the deterministic builder against the digest-bound sources, inspect the
packet diff, run affected backend/frontend qualification, prove a fresh
zero-to-head PostgreSQL migration and drift-free single head, and confirm the
branch reconciles current protected authority. Real candidate activation is a
separate owner authorization and is not included in this packet.

