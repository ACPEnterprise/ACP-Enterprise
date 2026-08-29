# HCP.MIGRATION.2J repair application boundary

HCP child repair is executed through the existing `HcpMigration2Application`.
There is no manual repair-plan or domain-run entry point.

The application classifies the target as one of:

- `NO_MASTER`
- `MATCHING_INCOMPLETE_MASTER`
- `MATCHING_INCOMPLETE_MASTER_WITH_ACCEPTED_REPAIR_PLAN`
- `COMPLETED_MASTER`
- `CONTRADICTORY_MASTER`
- `MULTIPLE_UNEXPECTED_MASTERS`

An accepted repair authority binds the master, original plan and digest, repair
plan digest, and the four original child identities. The application rebuilds
the repair plan through the 2I qualifier using durable Customer and native
Location identities. It never reconstructs repair commands independently.

The repair lifecycle preserves the original nonconforming Operational and
Financial children, creates deterministic generation-one repair lineage, runs
Operational repair before Financial repair, and records plan-conformance
admissions separately from execution completion. Existing conforming Customer
and History children are reused. A repaired child is eligible for master close
only when its admission is `PLAN_CONFORMING`.

The final completion transaction persists the 594 approved HOLD outcomes and
the original plus requalified plan outcomes before master attestation. Its
attestation binds both plan digests, original and repaired child identities,
repair generation, and the final requirements digest. Any mismatch leaves the
master incomplete.

Completed replay rebuilds both plans and verifies repair lineage, conforming
admissions, HOLD/outcome cardinality, and the requalified completion envelope.
It does not rerun domain persistence or create another repair generation.

Only safe counts, UUIDs, digests, classifications, and error codes may leave
the application boundary. Protected SOURCE.4 rows and financial payloads are
never included in application results or error messages.

This milestone does not execute the retained real repair. Owner authorization
for the next bounded step must invoke this application with the accepted repair
authority against the isolated loopback rehearsal target.
