# OM1 Migration checkpoint

Updated: 2026-09-12 17:00 UTC

- Mission commit: `0c08f1e3634f38a7fb82970932dea5de7a4cf24f`
- Mission file SHA-256: `03b74b5f065694b487268bdee531d8d50620f2816f30c91d8b665f9d5b3e9dfc`
- Current protected and deployed authority:
  `b5dff4b0203fe9a725a0ff844279876f410cba12`
- Native Location classifier integration: `681a7595` (PR #208)
- Pull request: #198

## Current Preview classification

The current fail-closed dry-run inspected the single actual restored Preview legacy
scope in a read-only transaction. It balanced all 4,970 known identity projections
plus all 1,540 native Locations owned by that Customer population:

| Domain | Exact successor | Ambiguous hold | Conflict |
| --- | ---: | ---: | ---: |
| Customer | 1,806 | 263 | 0 |
| Contact | 1,800 | 19 | 0 |
| Service Location | 1,515 | 25 | 0 |
| Job | 0 | 305 | 0 |
| Appointment | 0 | 266 | 0 |
| Invoice | 0 | 253 | 0 |
| Payment | 0 | 258 | 0 |
| **Total** | **5,121** | **1,389** | **0** |

Canonical report digest:
`ddf33badaa56e18948718946d52ca30203935c971396e34d86db9b49811f3be7`.
Canonical admission is false. No admission packet may be executed while the 1,389
holds remain. Customer-bounded Location fingerprints are now part of the record-level
manifest rather than separate advisory evidence.

After Enterprise deployed the integrated runner, a fresh protected-authority run
reproduced the same report digest and qualified-manifest digest
`2b7ecaa001a433eb6e57bab1a4d3c1547ed04f00efc2df42e552f24ae2039853`.
Its new replay packet digest is
`f012b45f15e9ce33744d90c3d5625c700271b30b48172c5b44cd88ca38d23395`.
The immutable host artifacts are retained under
`preview-run-20260911-protected-0b74c765`; file SHA-256 values are:

- admission packet: `b04fd46ac84aec6e0fd99af42742cfed56278bd0b11013fd40f18c2fd4e4b0f8`;
- record-level classification: `6c949d2a9f18d0c4f6646b8f7da724bd62170ebd5a3216ced906f9f4ed9673bb`;
- qualified successor manifest: `d907ea11c1473e7c52ad599393b54491c816c503216fb2cfb4536015e0b9d3d4`.

The packet names Enterprise as execution owner and records
`canonical_admission_allowed=false`; the admission executor was not invoked.

## Source currentness

The GET-only refresh completed at `2026-09-11T00:59:57Z`. Its manifest digest is
`7478262283ea1ab212b8bafa1fad0366c11156da73c43215cfa0bad45eb20160`.

Since the August 27 SOURCE.4 seal, HCP shows 50 added/1 removed/20 changed Customers;
48 added/262 changed Jobs; 14 added Estimates; 43 added/24 changed Invoices; and one
added Employee. The 48 added Jobs include 11 scheduled, 2 needs-scheduling, 2 in
progress, 31 completed, and 2 provider-cancelled records. SOURCE.4 is therefore not a
current-through-September-11 population and must not be presented as one.

The bounded per-Job GET refresh then inspected all 310 added or changed Jobs. Its
immutable manifest digest is
`2ca72931b3986c31eba9341bc06cc48477bdf511f5436ce5033b4ec7c8559f46`.
It accounts for 268 successful appointment relationship responses and 42 explicit
provider HTTP 400 holds; no response was silently discarded. The successful reads
returned 360 Appointments, including three dated September 11 and seven later
Appointments through September 18. Arrival windows are 354 at 120 minutes, three at
240 minutes, one at 60 minutes, and two at zero minutes. Technician disposition is
172 fully mapped, 187 with at least one identifier absent from the current eight-
employee authority, and one unassigned. The corrected calendar addendum derives its
dates from provider `start_time` because provider `start_date` is null in this response
set; its digest is
`f578b25ba3792218f729ce880a27be31ab8c4200edd451be040b1ad31a5a06b7`.

## Next action and gates

Enterprise has integrated and deployed the complete Location classifier but must not
execute Preview admission. Operational graph analysis found no
mechanically sufficient Job match beyond the already reported Customer/Location
parents, so the 305 Job holds and their dependent records remain intact. Post-admission
Customer/Location/Job/Appointment and calendar-lane verification remains pending
because SOURCE.4 is not admitted. No Production, HCP mutation, destructive
replacement, or financial posting occurred.

A final correlation-exhaustion pass confirms that the held legacy keys are control,
spreadsheet, or synthetic projection identifiers rather than SOURCE.4 provider IDs;
they cannot safely be promoted to authoritative provider identifiers. Among content-
correlated domains, the 263 held Customers comprise 259 with no positive candidate
and four with only non-unique candidates; the 19 held Contacts have no positive
candidate; and the 25 held Locations comprise seven with no positive candidate and
18 with only non-unique candidates. Converting any of these holds to unrelated or
exact would therefore require new authoritative evidence, not another deterministic
pass over the current inputs.

## September 12 current operational packet

The GET-only refresh completed at `2026-09-12T16:49:00Z` with digest
`a2c427ccc8f99f33a2340fa84118f987d75f1997afc8f0c7cf7fc27123e87748`.
Since the September 10 refresh it found five new and three changed Customers; one new
and 16 changed Jobs; one new and five changed Estimates; two new and two changed
Invoices; and no Employee change. Relative to sealed SOURCE.4, the current evidence
contains 55 added Customers, 63 added Locations, 49 added and 262 changed Jobs, and
45 added and 25 changed Invoices. Estimate payload volatility remains explicit: 15
are added and all 1,307 common records differ at the raw-payload level.

The bounded open-work appointment refresh read all 377 currently open Jobs plus every
Job changed since September 10: 383 of 383 provider relation requests succeeded and
returned 479 Appointments. Compared with sealed SOURCE.4 within this scope, 47 IDs are
new, six changed, and 426 are unchanged. The packet records 187 fully mapped and 292
partially unmapped appointment technician dispositions. All 40 referenced Customers
missing from the list endpoint resolved through sanctioned detail GETs. Twenty-two
open Jobs still have no provider Location ID after a successful Job-detail lookup.

The immutable current decision digest is
`5070aa62a8a86bfbd1249588e86f1f08d29ae433803ba05fdf8ee04b234e9025`
(file SHA-256
`f4649503ef079703641bc7593a2afd33c2464ac4ff0dddc27aaa4183ff51a77d`).
It is retained on the Preview host below
`source4-classification/current-20260912`. Canonical admission remains false. The
deployed executor accepts only the sealed historical package, no current overlay;
1,389 legacy projections still create duplicate-native-truth risk; 170 unique
invoice-number-linked Job/Invoice candidates have native field drift; a current
backup and verified restore receipt are absent; the 22 open Location parents are
unresolved; and 292 Appointments contain at least one unmapped technician. The
admission executor was not invoked.

## September 12 blocker burn-down

This pass remained read-only against HCP, QBO, and Preview and did not invoke either
admission executor. The accepted starting gate was 1,389 ambiguous legacy projections,
170 Job/Invoice drift candidates, 22 open Jobs without a provider Location identity,
292 Appointments containing 452 unmapped technician assertions, an absent current
overlay executor, and an absent current backup plus verified-restore receipt.

The 1,389 legacy holds are now partitioned without changing their authoritative
classifier disposition:

| Operational partition | Count | Mechanical basis |
| --- | ---: | --- |
| A. current-operation blocking | 13 | legacy Appointment projections whose uniquely invoice-bridged parent is current-open, but with no exact SOURCE.4/current window match |
| B. financial/historical blocking | 511 | 253 Invoice and 258 Payment projections; no financial truth was overwritten |
| C. legacy non-operational hold | 659 | 263 Customers, 19 Contacts, 25 Locations, 99 unbridged draft Jobs, and 253 remaining non-current Appointment projections |
| D. mechanically resolvable | 206 | unique legacy Invoice number to current HCP Invoice to HCP Job graph bridge: 15 current-open and 191 historical-closed Jobs |
| E. owner/policy decision | 0 | no new policy choice was inferred |

The 206 Job bridges are identity evidence only. For the 15 current-open bridges,
Preview confirms zero held Customer parents and zero held Location parents. Exact
arrival-window comparison resolved none of the 192 legacy Appointment candidates
under bridged Jobs (`0` unique, `0` non-unique, `179` no exact window, `13`
current-open parent), so no Appointment identity was guessed. The mechanically
resolvable partition reduces unresolved legacy projections from 1,389 to 1,183;
only the 13 Appointment holds intersect the legacy current-open scope.

All 170 previously qualified Job/Invoice drift candidates retain exact identity
reuse. The safe field rule is split by authority: HCP-owned Job operational state,
description/problem, schedule/window, cancellation, and provider relationship fields
may be compare-before-write overlay assertions; ACP-generated display identifiers
remain native; Invoice/payment status, amounts, tax, balance, and line economics
remain financial holds subject to QBO/accounting authority. Thus the candidate-level
accounting is 170 identity reuses, 170 safe Job-side overlays, and 170 Invoice-side
field holds (overlapping layers of the same 170 pairs, not 510 records). No owner
decision is required to preserve the financial fields as holds. A record-level field
merge packet still must be generated by the concrete Preview adapter before execution.

The 22 open Jobs remain individually isolatable holds: all 22 Job detail reads
succeeded, but each returned a null provider address identity and an entirely empty
address payload; each referenced Customer detail also exposed zero usable addresses.
There are 17 scheduled and five needs-scheduling Jobs. Customer identity alone cannot
prove a Location identity, so `0` resolved, `0` conflicting, and `22` remain
`HOLD_MISSING_LOCATION_PROVIDER_ID`. They do not justify blocking unrelated Jobs.

The current employee roster contains eight provider identities. Of 479 Appointments,
187 have only roster-present technician IDs. The other 292 contain 452 assertions for
26 provider IDs absent from the current roster; all 292 appointments are historical
relative to September 12. The safe disposition is therefore 187 exact-mapped
Appointments, zero merely name-supported mappings, 292 historical/retired-source
technician Appointments, zero currently active-but-unmapped, and zero ambiguous.
Admission may retain those 292 Appointments as unassigned with the original source
technician IDs queryable; absence from the roster is not permission to invent an ACP
Employee match.

The new `hcp-current-overlay/v1` contract keeps the sealed SOURCE.4 digest separate
from an independently hashed delta and carries per-record provider identity, source
digest, acquisition time, explicit create/update/removal/hold assertion, parent keys,
and duplicate fingerprint. Its executor requires the expected base authority and a
64-character rollback-backup digest, executes native changes and the immutable receipt
in one repository transaction, uses compare-before-write updates, rejects duplicate
fingerprint ownership, records removal without deletion, and replays an identical
durable receipt idempotently. Focused tests cover create/update/hold/removal, replay,
tamper, parent closure, base-authority drift, stale updates, and duplicate creates and
updates. The contract is qualified locally; a concrete Preview repository adapter is
intentionally not deployed or invoked by this change.

`CURRENT_OPERATIONAL_ADMISSION_ALLOWED = FALSE`: the exact remaining execution gates
are the concrete Preview adapter/record packet, the 22 isolated Location-less open Job
holds (if complete open-Job visibility remains mandatory), and the Enterprise-supplied
current backup plus verified-restore receipt. The 13 legacy current-open Appointment
holds remain bounded and must be represented as held legacy truth, not matched.
`FULL_HISTORICAL_FINANCIAL_ADMISSION_ALLOWED = FALSE`: in addition, 511 explicit
financial projections and the financial side of the 170 drift pairs remain held.

## September 12 operational admission finalization

The concrete SQLAlchemy overlay repository now binds `hcp-current-overlay/v1` to a
completed SOURCE.4 master run and an existing domain-service composition. It owns the
database transaction, locks the master row, delegates native create/update work to
the authoritative services, rejects native-identity replacement, and persists source
state, fingerprints, non-mutating assertions, journals, and receipts under the
master-run replay authority. Re-execution retrieves and verifies the same receipt.
It cannot run outside its transaction or against an incomplete SOURCE.4 master run.

The private record-level merge packet has manifest digest
`e23b7bcf5ac34ea650184afacc711af0c7028e83a6b1f7405e2ae17e13441eb2`
and file SHA-256
`ce9d4ea1e048a70b7a8a5b85fab33fd1a0568eb5cb1356229187144ab8bc7558`.
It contains 503 current operational assertions: 55 Customer creates, 20 Customer
updates, one non-destructive Customer removal assertion, 63 Location creates, 49 Job
creates, 254 Job updates, eight Job holds, 47 Appointment creates, and six Appointment
updates. The other 14 Location-less Jobs are unchanged sealed records and remain
bounded by the separate hold packet rather than being incorrectly represented as
delta mutations.

The private record-level hold packet has SHA-256
`c13cb0b565d2b86d34365f12d565f37f0e7ba6ec6bfa0d65de7f4a81ee088324`.
For the 13 legacy Appointment holds, every native record is an undated, unassigned
draft. Ten bridged provider Jobs expose a specific historical provider Appointment;
because the draft has no time/window identity, neither exact reuse nor safe unrelated
creation is provable, so those ten are `HOLD_DUPLICATE_RISK`. Three provider Job
relations expose no Appointment and remain `HOLD_INSUFFICIENT_EVIDENCE`. None is
current or future September 12 calendar work. Counts are therefore: exact reuse zero,
safe create zero, safe update zero, duplicate-risk hold ten, and insufficient-evidence
hold three.

All 22 Location-less open Jobs are `SAFE_OPERATIONAL_HOLD`: the Job identity,
Customer identity, status, and source evidence remain in the hold packet while the
other operational records proceed. The existing Job and Appointment models require a
real `service_location_id`, so `SAFE_ADMIT_WITH_LOCATION_UNRESOLVED` is zero; inventing
one is prohibited. `TRUE_GLOBAL_BLOCKER` is zero because the held Jobs have no parent
role for unrelated source records and the overlay parent guard excludes them and their
children from mutation.

`CURRENT_OPERATIONAL_ADMISSION_ALLOWED = FALSE`. The SQLAlchemy control/provenance
adapter and complete private source packet exist, but the production implementation of
its `CurrentOverlayDomainServices` port and the guarded execution command are not yet
bound. Claiming the packet executable before that native transformation/service layer
exists would bypass the required persistence boundary. After that bounded integration,
the only external execution gate is Enterprise supplying and binding the fresh Preview
backup digest, isolated verified-restore receipt, and current deployed/protected
authority. Historical and financial admission remains false. No Preview, HCP, QBO, or
Production mutation occurred during packet construction.

### Current-calendar acceptance projection

The September 12 relationship artifacts contain 18 current-or-future Appointments
across 15 Jobs, 11 Customers, and 11 provider-identified Locations. All 18 Jobs are
scheduled, all 18 Appointment technician assertions use one of the eight identities
in the current provider roster, and none intersects the 22 Location-less Job holds.
Five Job/Appointment pairs are unchanged from sealed SOURCE.4; ten Jobs and their
Appointments are new; and three existing Jobs have changed while their Appointments
are new. The remaining 461 bounded-scope Appointments are historical. This establishes
the post-admission acceptance baseline without treating historical holds as current
calendar blockers.

Protected integration must exercise the domain-service composition with PostgreSQL,
including: zero-to-head and current=head schema checks; create and compare-before-write
update paths for each operational domain; parent hold propagation; duplicate source and
native-fingerprint rejection; same-packet replay; stale prior-digest rejection;
transaction rollback before receipt persistence; receipt recovery after commit; and a
second execution proving zero additional native rows or events.

## September 12 transaction-safe native overlay execution

`HcpCurrentOverlayNativeServices` now provides the concrete production composition.
Customer and Location creates use the existing migration-scoped Customer service;
Job creates and Appointment creates/linking use the existing Job and Scheduling
services. Customer, Job, and Appointment mutation services expose a caller-transaction
method while their public methods retain transaction ownership. The overlay therefore
uses the same validation, locking, optimistic version checks, Business Event staging,
and parent-reference checks without nesting transactions or copying domain logic.

SOURCE.4 identities are appended under `housecall_pro_source4`; legacy
`housecall_pro` identities are not rewritten. Existing database uniqueness constraints
reject one SOURCE.4 identity targeting multiple native rows or one native row receiving
multiple SOURCE.4 identities. Exact replay resolves the persisted source state and
durable receipt. Current overlay digest/acquisition metadata remains queryable on
Location, Job, and Appointment lineage and in the master-run replay journal. Customer
lineage remains bound through its authoritative source-identity table and the same
durable overlay journal.

Updates are compare-before-write. Customer and Job updates hold when the native
`updated_at` is newer than source evidence. Job lifecycle must agree and only draft or
ready metadata can update; completed/cancelled work is never reopened or overwritten.
Appointment rescheduling is limited to scheduled/confirmed native work with an exact
source window; unsupported lifecycle evidence is held. Cancelled creates, incomplete
Locations, removal assertions, the 13 historical Appointment ambiguities, and the 22
Location-unresolved Jobs remain non-mutating evidence. An expected domain hold is
journaled and does not broaden into an unrelated operational failure; an unexpected
validation/error rolls back the entire overlay transaction and receipt.

The guarded command is:

```text
python -m app.operational_migration.hcp_current_overlay_command \
  --authority-file /protected/path/hcp-current-overlay-authority.json \
  --authorize-preview-execution
```

The 0600 authority file binds the deployed repository SHA, one expected schema head,
exact Preview database, Company/Branch/actor and SOURCE.4 child-run identities,
overlay file and manifest digests, hold packet, canonical classifier file and result,
base SOURCE.4 digest, fresh backup file/digest, verified isolated-restore receipt,
zero-drift/current-operational gate, and a deterministic idempotency identity. Runtime
Preview/Production flags, migration permission, source-run scope, and a PostgreSQL
transaction advisory lock are also fail-closed. The durable receipt context records
authority/schema/backup/overlay/hold/classifier digests, scope, attempted identities,
timestamp, idempotency identity, and success, while the receipt journal records every
created/reused/updated/held outcome. Rollback is the single database transaction for
the overlay plus Enterprise's digest-bound full-database backup restore.

The current-calendar dry-run acceptance baseline remains exactly 11 Customers, 11
Locations, 15 Jobs, and 18 Appointments. All 18 have provider Locations and mapped
technician source assertions; expected current-calendar technician and Location holds
are zero. The 461 historical Appointments, 13 legacy Appointment holds, and 22
Location-unresolved Job holds remain separately reconciled and absent from active
current-calendar truth. Enterprise post-admission verification must prove exact source
identity continuity and local date/window/status equality through Customer -> Location
-> Job -> Appointment, then exercise Schedule Month/Day/Week/Work Week and Dispatch
read projections without creating dispatch assignments.

Qualification used Python 3.12.13 and PostgreSQL 16.14 in an isolated local database.
The database was created empty and upgraded zero-to-head; `alembic current` and
`alembic heads` both reported the single head `d4f6h8j0l2n4`. Focused Customer/Job/
Scheduling plus overlay tests passed 42/42, and the affected operational/customer
migration suite passed 275/275. No Preview execution occurred. Enterprise must repeat
the guarded PostgreSQL integration/replay tests after protected integration with its
fresh backup and isolated restore receipt before live execution.
