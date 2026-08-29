# HCP.MIGRATION.2D Employee and history closure

HCP.MIGRATION.2D adds no real HCP business data. It closes the final two
subordinate persistence paths required by the SOURCE.4 rehearsal.

## Employee candidate aggregate

`HcpMigration2Orchestrator.persist_employee_candidate` is the sanctioned
Employee path. A provider-native identity deterministically selects an
Enterprise Employee identifier. For `CREATE_ENTERPRISE_EMPLOYEE_CANDIDATE`, an
inactive Employee with no Membership, User, credential, payroll, compensation,
or permission assertion is inserted in the same transaction as its immutable
HCP crosswalk. A transaction failure leaves neither half committed. Exact replay
returns the same pair; changed source, receipt, disposition, scope, or target
identity fails closed.

`EXCLUDE_EMPLOYEE_HOLD_ASSIGNMENTS` writes only master-bound source evidence.
The database and command barriers prohibit an Employee target for that
disposition, so the LOKAL marketing identity cannot become workforce identity.

## Note/history subordinate run

The existing `CutoverMigrationService` remains responsible for history business
rules. The HCP orchestrator invokes it as the required `history` child of the
master. The child is bound by the same composite master, Company, Branch, and
actor foreign key used by Operational and Financial runs.

SOURCE.4 Notes require an authoritative provider Job source identity. A missing
parent is an explicit unresolved outcome; no similarity or proximity matching is
available. Persisted Notes bind native identity, source/package digest,
transformation contract, actor and partial-provenance metadata through the
history child. Changed evidence under an existing identity fails closed.

History entries are evidence only. They do not mutate Job lifecycle, schedule or
dispatch work, establish consent, assert attachment availability, or create
Accounting truth.

## Completion and recovery

Master completion now requires Customer, Operational, Financial, and History
children plus exact Employee candidate/exclusion and Note outcome accounting.
Interruption retains the child checkpoint and immutable evidence. Replay reuses
the same Employee, crosswalk, Note identity, child run and master; pre-cutover
rollback remains evidence-preserving and separately authorized.

Alembic revision `d7f1b3c5e068` adds `history` to the allowed SOURCE.4 child-run
domains while retaining a single migration head.
