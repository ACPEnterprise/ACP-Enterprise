<!-- markdownlint-disable MD013 -->

# Phase-1 Operational Integration Checkpoint

- **Milestone:** `BANK.PLAT.001`
- **Status:** `COMPLETE`
- **Authoritative evidence SHA:** `0f6559ecddb7ca3854c79ea7b5cb31432318976a`
- **Checkpoint date:** 2026-08-28
- **Environment:** disposable local PostgreSQL and Redis only
- **Preview/Production:** untouched

## Decision

The authoritative Phase-1 operational domains compose without a product, schema,
security, or ownership defect. The checkpoint passes its implementation and local
validation boundary. The owner's acceptance completes `BANK.PLAT.001` and satisfies
the integration-checkpoint dependency of `BANK.PUR.002` (`PUR.2`). The fingerprinted
bank authority snapshot records that completion without changing readiness runtime
logic. This document does not Start `PUR.2`.

## Authoritative inputs

| Capability | Evidence | Checkpoint disposition |
| --- | --- | --- |
| CRM and Service Locations | `b75f9b6507f51c1e60dc23861012a77cad2ce804` | Compatible |
| Jobs / `OPS.1` | `c89396546a6ba6012e48694ba7737bd30e316637` | Compatible |
| Scheduling | `c64519305ba4878090add5ae986d86e9a883a9d7` | Compatible |
| Dispatch / `DISP.2` | `98ae82579d23d8b3737cce590186b93b865ef022` | Compatible |
| Technician field execution | `4ed07803e8ad8b220c96ffcd1980db9af0a63ddc`, corrected by `4ad60c0d29c43493bb5b37893522fc28c7225ce9` | Compatible; physical acceptance remains separate |
| Inventory foundation and `INV.3-LEGACY` | `d892cf96249083908317bc814f6b460940a91def`, `9c2b114cb658be0454bbb36bdf0e5929ecc7e0e5` | Compatible historical Inventory authority |
| `INV.2A` | `45fda1c0fe8645a6fcdbae0cc4f2e993bbeb1e1a` | Compatible |
| Price Book | `e97dc408742e0037330b79156cd0a5ba583c6649` | Compatible provenance owner |
| Estimates / `EST.4` | `62c0d84cd33cd5851a9a70db3dfbde67a09ce343` | Compatible commercial authority |
| Invoice / AR | `43018e22786341116f77a606ccf70a8fa1e3ae14` | Compatible |
| Payments | `8c107087b85f0e6c08a58ec63d3099e2693d5d82` | Compatible external-processor accounting boundary |
| Purchasing / `PUR.1` | `88285c7c0879d8df7b42659a9d25c64e5b58a27b` | Compatible; checkpoint dependency satisfied |
| Platform controls | `bd034a393f045c8b66bd2e48e37f996c809b50c0` | Compatible |

All listed commits are ancestors of the authoritative evidence SHA.

## Intervening-commit reconciliation

| Commit | Classification | Meaningful checkpoint effect |
| --- | --- | --- |
| `65377ad5cba31c0945324965f81dd60e7102174c` | A | Accounting integration-candidate evidence; no Phase-1 operational or schema effect |
| `b691f887e41d25c3ea721b8fa85133ffbffae961` | B | Adds the deterministic bank authority/readiness contract used to record completion |
| `db84c12c485f21be4f607ff26fdbd0e2844bc433` | B | Accepts the readiness evaluator in the bank authority snapshot |
| `1d00919c95a9143e7d0c4f52eebf899e2c71c7f0` | C | Refreshes scheduler proof identities; scheduler tests require affected validation |
| `a9f0c8832b4548bf5699b7cb9dd49beb5690d15d` | A | Mechanical merge of the compatible readiness changes |
| `f4428b8dde7c33f640042b4bf8aa50303c9981d1` | A | Economics policy decisions only; outside Platform runtime scope |
| `766d45416ec3705eb750d88620d30cbaaf8f93ca` | C | Adds Economics policy persistence and permission codes; advances the migration head |
| `ca4f7151f7091617ccee1567b91dd28a982e0802` | C | Expands Economics policy persistence; advances the migration head |
| `05474f1b72d310588b06c994e8d9f1caab81890c` | C | Engineering Control stale-dispatch hardening; requires affected control-plane regression only |
| `e55cc71994c4efac81562bbebfcfbb63fedf49d0` | C | Registers All County Economics policy gaps; advances the migration head |
| `0f6559ecddb7ca3854c79ea7b5cb31432318976a` | A | Adds Beacon operational exception catalog; no schema or Phase-1 operational ownership effect |

None changes Customers, Scheduling, Jobs, Dispatch, Field Service, Inventory,
Purchasing, Price Book, Estimates, Invoicing, Payments, AP, Accounting runtime,
or their ownership contracts. The three Economics migrations are linear and require
fresh upgrade, current-head, and drift validation; they do not expand this milestone
into Economics policy work.

## Composition results

Company and Branch scope remains explicit across Jobs, Scheduling, Dispatch, Field
Service, Inventory, Purchasing, Invoice, Payments, AP, and Accounting. Authorization
is evaluated before domain mutation; cross-Company and unauthorized Branch evidence
is not treated as valid integration input.

Scheduling owns appointment time and itinerary evidence. Dispatch owns assignment,
acknowledgement, en-route, arrival, and reconciliation state. Jobs owns work-state
transitions. Field Service composes those owners through assignment-aware commands
and a generic Job completion guard rather than duplicating their rules.

Price Book component identity is descriptive commercial provenance, not an
Inventory item. Accepted Estimate and Estimate-to-Job conversion evidence provide
commercial authorization for field completion. Field completion requests the
existing Invoice handoff without creating Invoice or Payment truth. Invoice owns AR;
Payments owns processor-result, application, refund, deposit, clearing, settlement,
and reconciliation facts.

Inventory owns physical identity, custody, quantities, reservations, allocations,
movements, and material-issue evidence. Purchasing owns Vendor and PO identity and
lifecycle. The `PUR.1` validation proves it does not write Inventory, AP, Accounting,
or Journal persistence. `PUR.2` must continue to request Inventory-owned receipt
movements through an accepted public seam; it may not write Inventory tables.

Business Events use the central catalog and transactional staging service. Field
completion and Job completion share correlation evidence. Domain events retain
Company, Branch, entity, actor, and domain-owned payload boundaries. No parallel
event mechanism was found.

Idempotency identities are Company-scoped and contradictory replay fails closed in
the validated operational services. Optimistic versions or scoped row locks protect
Job, Dispatch, Field, Inventory, Purchasing, Invoice, and Payment transitions.
Failures remain rejected, pending, or reconciliation-required rather than being
reported as successful.

## Technician milestone reconciliation

`TECH.FIELD.1` satisfies the runtime substance of `BANK.FIELD.007` (technician
job-status transition journey): assigned itinerary, acknowledgement, en-route,
arrival, start, pause, resume, completion, authorization, replay protection, and
concurrency are authoritative. `BANK.FIELD.007` therefore requires no duplicate
implementation after owner acceptance of this checkpoint evidence.

`TECH.FIELD.1` overlaps substantially with roadmap `TECH.2`: status execution,
append-only notes, customer disposition, immutable completion evidence, generic Job
completion protection, Invoice handoff, role/Branch isolation, and mobile failure
state are implemented. It does not prove every optional roadmap interpretation of
photos or forms. The Day-1 contract makes such artifacts conditional on a versioned
Job requirement and defers generalized forms/media tooling. Consequently:

- Day-1 `TECH.2` execution scope is satisfied by `TECH.FIELD.1` for integration and
  dependency purposes.
- Physical-phone acceptance remains open and cannot be inferred from this local
  checkpoint.
- Any generalized forms, media, or optional technician polish remains a distinct
  future packet; it must not reopen the accepted Day-1 runtime.

## Job material boundary

- `INV.3-LEGACY` is complete historical Inventory-owned reservation, allocation,
  material-issue, reversal, and stock-control evidence.
- `JOB.MATERIAL.1` is the not-started future Job-owned material-requirement and
  append-only actual-use evidence milestone.
- Job-owned actual-use evidence may precede `PUR.2`; later Inventory reservation and
  technician material-request integration remains governed by `BANK.INV.*` and
  `BANK.FIELD.*` dependencies.

This checkpoint implements neither boundary.

## PUR.2 release contract

The aggregate-integration prerequisite is satisfied: PUR.1's Vendor/PO ownership is
disjoint from Inventory stock truth, and Inventory exposes the domain that must own
future receipt movements. Once the owner accepts `BANK.PLAT.001`, `BANK.PUR.002` is
dependency-ready for a separately approved Start, subject to a current-origin fetch,
an isolated worktree, a machine-enforceable boundary, and serialized migration
integration from the then-current sole Alembic head.

`PUR.2` remains prohibited from direct Inventory-table writes, AP Bill creation,
Accounting posting, real import, Preview, and Production under this checkpoint.

## Schema and validation evidence

The authoritative migration lineage is linear and has exactly one head:

```text
z1q3l5n7r942
  -> a2r4m6p8s053
  -> b3s5n7q9t164
  -> c4t6p8r0u275
  -> d5u7q9s1v386
  -> e6v8r0t2w497
```

`b3s5n7q9t164` remains the authoritative `PUR.1` migration. Economics policy
authority advances the current head to `e6v8r0t2w497`. A fresh upgrade completed
through that head and Alembic reported no model drift. No migration or schema change
is required by this checkpoint.

Validation executed against disposable local services:

- 516 current-authority focused operational, platform, and bank-readiness backend
  tests passed across Jobs, Scheduling, Dispatch, Field Service, Inventory,
  Purchasing, Price Book, Estimates, Invoicing, Payments, AP, Accounting, Platform
  authorization, and deterministic milestone-bank authority.
- 218 frontend tests passed across 75 files; ESLint and the TypeScript/Vite
  production build passed.
- The prior reconciled full backend run passed 1,251 tests. Two unrelated Engineering
  Control tests failed: one synthetic successor uses a stale scheduler execution
  head, and one expected milestone-code set has not been updated for three new
  phone factory-proof entries. Those control-plane results do not change the
  486-test operational result, and this checkpoint does not modify Development
  Factory state.
- The refreshed bank authority/readiness suite passed 26 tests. Ruff passed on the
  changed Python boundary, and MyPy passed on all seven scheduler source files.
- Markdown, relative links, JSON parsing/fingerprinting, `git diff --check`, focused
  private-material scanning, and current-head/drift checks passed.

No product defect was found. The only required dispositions are milestone identity
reconciliation and the separately gated physical TECH.FIELD.1 acceptance.

## Gates preserved

This checkpoint authorizes no downstream Start, deployment, import, accounting
entry, Preview change, Production change, HCP/QBO contact, worker enrollment, or
Development Factory runtime mutation. `BANK.PUR.002` and `BANK.PLAT.002` are now
dependency-ready but each requires a separately authorized Start.
