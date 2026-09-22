# Laptop1 Pipeline + Money Integration Handoff

## Current authority

- Protected authority: `origin/customer-management-v1` at `63f9a133758bfb1ccb71a7bf0daf1b424da05752`
- Starting LaptopE head: `a344033785483e84a030bf8cb69aa1891f8bfae4`
- Resulting LaptopE head: recorded after this document is committed and pushed
- Protected ancestry: protected SHA is an ancestor; current relationship is 0 behind
- Canonical roadmap/schema authority remains OM1E-owned

## Integrated candidates

### Pipeline

- Branch: `work/pipeline-authority-1`
- Candidate: `bfc8041b63430f4dd07062d785bd38136fd4fa63`
- Disposition: integrated, with the worker’s Command Center route rewrite intentionally not replayed
- Included: canonical Company/Branch-scoped Lead authority, lifecycle transitions, CSR queue and next-action projection, append-only history, optimistic versioning, evidence-bound links, dedicated Pipeline UI/API, and migration `r4t6v8x0z2c5`
- Migration parent: `p2r4t6v8x1z3`, the current canonical schema seed in the roadmap
- Source-domain gaps remain explicit: Communications disposition intake, prospect-to-Customer binding, approved-not-scheduled Estimate authority, and Workforce CSR display names

### Money

- Branch: `work/money-authority-1`
- Candidate: `ac0dfb5b104b3bccab3c189ea5419062223470fb`
- Disposition: integrated
- Included: read-only `GET /api/v1/payments/money-position`, captured/collected/settled/deposited separation, actual settlement fee evidence, refunds/chargebacks, open-amount AR due-today evidence, truthful incomplete COD expectation, bank-unavailable state, and Company/Branch authorization
- No migration
- No payment, accounting, bank, or business-record mutation

## Command Center disposition

The protected PR #482 Command Center route was preserved. Pipeline’s conflicting dashboard rewrite was not replayed because it would replace protected behavior and still represented Lead data as unavailable. The dedicated Pipeline route is available for the next bounded Command Center consumer. Money has no dashboard consumer in this checkpoint; the endpoint is ready for a separate consumer-owned follow-up.

## Schema qualification

The Pipeline migration is mechanically based on `p2r4t6v8x1z3` and was integrated without rewriting the worker migration. The repository currently exposes multiple historical Alembic branch heads and the local environment has no Alembic runtime installed, so fresh zero-to-head/current-to-head/downgrade qualification and final single-head reline are not claimed here. OM1E must perform the canonical schema reline and release qualification before protected admission.

## Qualification

- Frontend affected tests: 4 files, 13 tests passed
- Frontend lint: passed
- Frontend production build: passed
- Backend Python compilation: passed
- `git diff --check`: passed
- Backend pytest: unavailable (`pytest` not installed); not represented as passed
- Preview/Beta deployment: not performed

## Automatic next assignments

- Laptop1-A: `PIPELINE.COMMUNICATIONS.INTAKE.1` — provider-neutral, idempotent disposition-to-Lead create/attach contract; no fuzzy Customer binding. If Communications remains provider-gated, deliver the independent prospect-to-Customer conversion contract instead.
- Laptop1-B: `MONEY.PAYMENT.TERMS.COD.AUTHORITY.1` — explicit Company/Customer terms, COD/NET classification, scheduled-value evidence, and due-date semantics; fail closed when contractual evidence is absent. Do not add bank or provider integrations in this milestone.
- Phone/Mobile: remains on the current Apple/TestFlight human gate; no Mobile implementation is required by this checkpoint.

## OM1E handoff

OM1E should consume the Pipeline and Money candidates independently from the cumulative LaptopE head, reline `r4t6v8x0z2c5` onto the canonical protected Alembic lineage, run backend migration and pytest qualification, and admit the read-only authorities only after schema and protected-release checks pass. OM1E owns final protected integration, Beta deployment, real-data acceptance, and release authorization.
