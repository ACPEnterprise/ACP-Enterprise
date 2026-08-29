# HCP.MIGRATION.2G execution plan

`HcpMigration2ExecutionPlanBuilder` is the sole protected SOURCE.4 plan
constructor. It verifies the sealed package, hybrid Customer authority, Job
parent closure, Migration.1 evidence, and all five owner receipts before
building deterministic commands for every accepted domain.

The builder emits no source rows. Its public summary contains only the plan
UUID/digest, contract version, counts, and outcome classifications. The plan
digest binds package and collection evidence, receipts, transformation
versions, Company, Branch, actor, ordered command digests, durable outcomes,
and reconciliation requirements.

`HcpMigration2Application` is the sanctioned entry point. It qualifies the
loopback target, proves the real-data baseline is pristine, constructs the plan,
and passes it to `HcpMigration2Runner`; operators do not manually assemble
Python commands.

Builder-classified records that cannot legally enter a domain service persist
as master-bound `hcp_migration_plan_outcomes`. These rows contain hashes and
classification evidence only, have no operational or accounting effects, and
keep exceptions, rejections, and intentionally non-applicable subjects in the
master reconciliation.

The schema head is `f3a5c7e9b102`. This milestone qualifies construction only;
it does not create a real plan run or persist HCP business rows.
