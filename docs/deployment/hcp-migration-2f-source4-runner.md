# HCP.MIGRATION.2F SOURCE.4 runner

HCP.MIGRATION.2F closes the Customer execution boundary without executing the
real rehearsal. The only sanctioned entry point for the future SOURCE.4 run is
`HcpMigration2Runner`. It verifies protected package and owner evidence, creates
or resumes the deterministic master, creates master-bound Customer staging, and
then delegates persistence to `HcpMigration2Orchestrator` and its existing
domain services.

## Customer staging and lineage

The runner constructs staging after the master exists. The staging identity is
deterministic over the master, SOURCE.4 package, hybrid-admission digest,
transformation digest, Company, Branch, and actor. Identical replay reuses the
artifact; changed evidence fails closed.

For each admitted Customer, Customer, Contact projection, complete Service
Locations, Customer lineage, and native `adr_` Location identities share the
aggregate transaction. Missing or contradictory Location lineage therefore
rolls back the aggregate. Location identity cannot cross Company, Branch,
Customer, or master scope.

The 294 incomplete Location assertions persist as master-bound child
exceptions. They remain separate from the 5,339 complete Locations and cannot
become operational Locations. The invariant is:

`5,633 acquired = 5,339 complete + 294 child exceptions`.

## Protected-output boundary

Protected evidence is read only by `ProtectedSource4Loader`. Its public result
contains counts, contract identities, and digests. Evidence failures use
`SafeEvidenceError(code, digest)`; paths and raw row values are not included in
exception or result text. Callers must not log protected input objects or use
raw exception representation from parsing libraries.

## Execution gate

The schema head is `e2f4a6b8c091`. A future HCP.MIGRATION.2 run must bind the
accepted hybrid digest and parent-closure digest in its master command and run
through `HcpMigration2Runner`. This milestone creates no real master, child run,
or HCP business row.
