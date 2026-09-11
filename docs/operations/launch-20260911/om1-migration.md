# OM1 Migration checkpoint

Updated: 2026-09-11 02:00 UTC

- Mission commit: `0c08f1e3634f38a7fb82970932dea5de7a4cf24f`
- Mission file SHA-256: `03b74b5f065694b487268bdee531d8d50620f2816f30c91d8b665f9d5b3e9dfc`
- Implementation base: `42a4f68087d76247269bd4c8388f556dd62a8b5c`
- Candidate: `56e38fcc6d321e4f92daa311b70cd82a0ebef352`
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

The replay packet with digest
`9c6980d9ce1d0b868b25e8f97db8c059e4071b017c465797c5a487d6db5f1c3d`
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
