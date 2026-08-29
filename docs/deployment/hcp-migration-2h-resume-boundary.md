# HCP.MIGRATION.2H event boundary and resume admission

The Customer admission boundary now distinguishes one admission decision per
authoritative Customer from the domain events emitted by the admitted aggregate.
For the sealed SOURCE.4 package the deterministic population is:

- 5,296 Customer admission events;
- 5,296 Customer domain events;
- 4,148 Contact projection events;
- 5,339 Service Location projection events;
- zero billing-address projection events;
- 14,783 aggregate domain events;
- zero audit or lineage events inside this pre-persistence boundary.

The population uses hashed source identities plus category and ordinal. Duplicate
event identities fail closed, input ordering is irrelevant, and the sealed
population digest is
`bad342ccb09303812cda817fedd8115921f7287e6f2bb41b8b2f8f1426a4c4e3`.
Audit and lineage remain mandatory persistence evidence but are not miscounted as
domain Business Events at admission.

`HcpMigration2Application` admits five explicit target states: `NO_MASTER`,
`MATCHING_INCOMPLETE_MASTER`, `COMPLETED_MASTER`, `CONTRADICTORY_MASTER`, and
`MULTIPLE_UNEXPECTED_MASTERS`. A matching incomplete run is rebuilt from its
original baseline and accepted only when master UUID, input and attestation
digests, plan digest, package, contracts, receipts, actor, Company, Branch,
schema, builder, source counts, and protected staging all match.

Staging qualification is read-only and proves the existing artifact UUID and
digest, 5,296 staged rows, 14,783 staged domain candidates, and 294 child
exceptions. Resume later calls the existing idempotent staging path; it neither
recreates the master nor duplicates staging or Location exceptions. Completed
masters are reserved for the replay path, and contradictory or multiple masters
fail closed with safe codes and digests.

This milestone does not resume business persistence. The retained master
`63273602-8619-5c0b-8b49-8537338b04b5` remains incomplete with its original
staging and exception evidence.
