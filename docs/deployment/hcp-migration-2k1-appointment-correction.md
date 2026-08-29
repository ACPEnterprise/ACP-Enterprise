# HCP.MIGRATION.2K1 Appointment sequence correction

`hcp-migration-2k1-appointment-sequence/v1` defines the authoritative target
projection for SOURCE.4 Appointments. Appointments are grouped by authoritative
Job and ordered by scheduled start, scheduled end, then provider-native
Appointment identity. The final identity is a stable tie-break; input order and
database insertion order never participate.

The sealed repair population qualifies 1,249 Appointments across 992 Jobs: 911
single-visit Jobs and 81 multi-visit Jobs. The multi-visit Jobs contain 338
Appointments (257 visits beyond the first); the maximum is 36. No ordering
ambiguity remains under the registered contract.

For the sealed rehearsal authority, the sequence population digest is
`9e77ed819ee488ac5114d6fda26d9ae422b081cdfa9785fb56bbf679d6fa7acb`.
The retained checkpoint is 38 = 32 reused + 6 correction-required, leaving
1,211 commands; its digest is
`3646dc75db78ac72ae54b6fc1b3cdcd03920d0d54795ab265689a37afbaf906b`.

## Evidence-preserving reprojection

The original repair plan remains immutable. A generation-2 sequence plan binds
the old repair digest, sequence contract and digest, retained checkpoint,
correction set, master, repair, Company and Branch. `visit_sequence` is a target
projection and never changes provider source identity or SOURCE.4 evidence.
For this authority the superseding plan ID is
`a39f3927-0f7f-59a4-8056-97077012832f` and its digest is
`167f3e3729c78953de2e12382d2b64572b0a42082780d1bba4651be0063c5fb5`.

Corrections are append-only evidence. Each row records the retained link,
prior and corrected sequence, failed child, source-identity digest, scope and
deterministic correction digest. Application is performed per Job under a row
lock. A temporary high positive sequence band and the final values are flushed
inside one caller-owned transaction, so the unique Job/visit constraint remains
enabled and no invalid intermediate state can commit.

Identical correction replay reuses the same deterministic evidence. Changed
scope, source identity, link identity or target sequence fails closed. Already
correct retained Appointments are checkpoints and are never rewritten.

## Resume boundary

The qualified checkpoint contains 1,094 accepted Jobs, 38 retained Appointment
identities, and the remaining deterministic Appointment commands. Financial
repair remains unavailable until Operational execution completes and receives
`PLAN_CONFORMING` admission. HCP.MIGRATION.2K1 does not apply corrections or
resume the retained rehearsal.

Protected rows never enter correction errors or public output. Only counts,
UUIDs, hashes, digests, sequence integers and safe error codes are permitted.
