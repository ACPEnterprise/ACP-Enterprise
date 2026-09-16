# ENTERPRISE.INTELLIGENCE.CURRENTNESS.1

## Evidence ledger

- Protected base: `origin/customer-management-v1`
- Observed protected SHA: `a65a104c21282fd8f94a2e9bac37ba576a91a75c`
- Integration branch: `integration/laptop1-intelligence`
- Worker consumed: `origin/work/beacon-luminary-realdata-acceptance-1`
- Worker SHA: `92be0b1d74a3023d9abbffd4fc3abaf5e4792036`
- Worker ancestry: direct descendant of the protected SHA
- Integrated code commit: `559f4e1412552f48b2e5eec81586aaa2a6b8ea55`

## Integrated capability

Beacon morning briefs now consume persisted evaluation-history deltas when a
completed run exists in the requested Company/Branch window. They expose NEW,
RESOLVED, CHANGED, and EXPIRED counts while retaining explicit limitations and
the existing read-only/source-domain boundary. Without completed history, the
brief remains truthful and reports comparison as unavailable.

## Qualification

- Ephemeral PostgreSQL migration `upgrade head`: passed.
- Focused Beacon tests: `5 passed`.
- Python compilation of changed modules/tests: passed.
- `git diff --check`: passed.
- No migration changed; no canonical Alembic head claimed.
- Frontend unchanged; frontend suite was not run because local `vitest` is not
  installed.

## Acceptance and release gates

- Preview health is reachable, but reports deployed SHA
  `a109743968fc764fc1885ecf8fbd4abeb87846d7`, not the current protected SHA.
- Authenticated Preview owner acceptance remains required.
- No real All County Beacon/Luminary result was accessed in this lane.
- OM1 ENTERPRISE.RELEASE owns final protected integration, migration reline,
  Preview/Production deployment, and owner acceptance authorization.

