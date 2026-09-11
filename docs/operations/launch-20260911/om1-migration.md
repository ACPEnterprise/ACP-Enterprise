# OM1 Migration checkpoint

Updated: 2026-09-11 02:00 UTC

- Mission commit: `0c08f1e3634f38a7fb82970932dea5de7a4cf24f`
- Mission file SHA-256: `03b74b5f065694b487268bdee531d8d50620f2816f30c91d8b665f9d5b3e9dfc`
- Implementation base: `42a4f68087d76247269bd4c8388f556dd62a8b5c`
- Candidate: `fcaecf35ed488464713e4a0e471c5853e70b7845`
- Pull request: #198

## Current Preview classification

The current fail-closed dry-run inspected the single actual restored Preview legacy
scope in a read-only transaction. It balanced all 4,970 known projections:

| Domain | Exact successor | Ambiguous hold | Conflict |
| --- | ---: | ---: | ---: |
| Customer | 1,806 | 263 | 0 |
| Contact | 1,800 | 19 | 0 |
| Job | 0 | 305 | 0 |
| Appointment | 0 | 266 | 0 |
| Invoice | 0 | 253 | 0 |
| Payment | 0 | 258 | 0 |
| **Total** | **3,606** | **1,364** | **0** |

Canonical report digest:
`6c680a0df23b4d761ed3771225554a452d43aab48906d9b6225f48601984e9d8`.
Canonical admission is false. No admission packet may be executed while the 1,364
holds remain. A separate graph analysis found 1,533 exact Customer-bounded Location
fingerprints, but those results are not promoted into the manifest until the complete
Location/native-truth population is represented by the runner.

The replay packet with digest
`0367433ce36e9cce70a7b0317b60a259437b5bc5fa0db121c686f47c872060fc`
is retained on the Preview host as protected operator evidence. It names Enterprise
as execution owner and records `canonical_admission_allowed=false`.

## Source currentness

The GET-only refresh completed at `2026-09-11T00:59:57Z`. Its manifest digest is
`7478262283ea1ab212b8bafa1fad0366c11156da73c43215cfa0bad45eb20160`.

Since the August 27 SOURCE.4 seal, HCP shows 50 added/1 removed/20 changed Customers;
48 added/262 changed Jobs; 14 added Estimates; 43 added/24 changed Invoices; and one
added Employee. The 48 added Jobs include 11 scheduled, 2 needs-scheduling, 2 in
progress, 31 completed, and 2 provider-cancelled records. SOURCE.4 is therefore not a
current-through-September-11 population and must not be presented as one.

## Next action and gates

Enterprise may integrate the runner but must not execute Preview admission. OM1
Migration next owns complete Location classification and any mechanically supported
operational graph correlations. Post-admission Customer/Location/Job/Appointment and
calendar-lane verification remains pending because SOURCE.4 is not admitted. No
Production, HCP mutation, destructive replacement, or financial posting occurred.
