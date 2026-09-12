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
