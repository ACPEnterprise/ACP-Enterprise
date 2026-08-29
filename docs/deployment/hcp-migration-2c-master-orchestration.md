# HCP.MIGRATION.2C master orchestration

HCP.MIGRATION.2C closes the child-run escape path found by the first real
MIGRATION.2 preflight. It adds orchestration infrastructure only and persists no
real HCP business record or rehearsal run.

## Master and child runs

The sanctioned `HcpMigration2Orchestrator` validates the exact credential-less
actor, Company, Branch, loopback database identity, schema, SOURCE.4 package,
transformation versions, and five receipts before creating the deterministic
master. It is the only SOURCE.4 application composition boundary.

Customer runs and the Operational and Financial runs use
`housecall_pro_source4`. Database checks require a master for that source-system
identity. Composite foreign keys bind master, Company, Branch, and actor; one
Customer run and one Operational/Financial run per domain are permitted under a
master. Unrelated provider-neutral migration workflows remain nullable and
compatible.

Master completion requires all three child domains to be terminal and
successful or successful-with-exceptions. It also verifies Customer lineage,
seven Employee crosswalks, exact HOLD populations, unlinked Estimate evidence,
and complete source outcome accounting. The master records child identities and
cannot complete on missing children, missing evidence, or aggregate mismatch.
One package may have only one master input per Company/Branch, so changed
package, receipt, transformation, actor, scope, or count evidence cannot fork a
second resume path.

## Transaction and recovery model

The master and every child checkpoint are durable transactions; the migration
does not use one enormous transaction. Each domain retains its existing
record-level transaction and idempotent source identity behavior. Interruption
marks the master incomplete and retains the last checkpoint, business rows,
immutable audit/source evidence, dispositions, and HOLD state for deterministic
resume. A partially completed master can never be represented as completed.

Pre-cutover rollback is evidence-preserving: automatic destructive deletion is
not authorized. Business candidates remain isolated pending a separate bounded
rollback or cutover decision, while source evidence, receipts, lineage, and HOLD
records remain immutable. Holds never enable operational effects or establish
accepted financial truth.

## Non-operational evidence

Real `UNLINKED_NON_OPERATIONAL_ESTIMATE` evidence requires the master and remains
Job-less, non-operational, and non-accounting. The single existing qualification
fixture is explicitly marked `synthetic_qualification`; it is the only permitted
master-less row.

Alembic heads `b5d9f1a3c846` and `c6e0a2b4d957` implement these constraints.
The isolated rehearsal target remains at zero real HCP business rows and zero
real master/child runs after qualification.
