# HCP.MIGRATION.2 release gate

All five HCP.MIGRATION.1A owner decision groups are sealed. The Branch binding
maps both the native `Plumbing` Business Unit and the explicit missing-Business-
Unit pattern to the isolated primary Branch while retaining the original HCP
classification. The 24 reviewed Estimates are bound to the
`UNLINKED_NON_OPERATIONAL_ESTIMATE` exception contract through the existing
`MIGRATE_UNLINKED_EXCEPTION_IF_SUPPORTED` alternative; no Job link or
operational/accounting effect is authorized.

MIGRATION.2 persistence remains fail-closed. The current repository explicitly
registers no real HCP operational transformation contracts. Its authoritative
tests require HCP Job, Appointment, Estimate, Invoice, Payment, Note, and
Attachment layouts to return `unsupported_export_version`. The protected
candidate package contains identity, digest, relationship, disposition, and
exception metadata, not the registered domain-value transformations needed by
the persistence services.

The isolated target also has no User or Membership. Existing Customer,
Operational, and Financial migration services require an authorized actor and
persist migration-run foreign keys to that actor. Supplying a nonexistent ID or
constructing a synthetic authorization context would bypass the architecture.
The general platform bootstrap would introduce administrator credentials,
roles, and permissions beyond the previously sanctioned Company/Branch-only
prerequisite.

Finally, Enterprise Estimates currently require a Job parent. Although the 24
source records and their owner disposition are preserved, there is no approved
target persistence model for a discoverable, non-operational, unlinked Estimate.

No migration run was started. The next bounded milestone is
`HCP.MIGRATION.2A — Persistence Contract and Rehearsal Actor Qualification`:
register and test the acquired HCP layouts, add the non-operational unlinked
Estimate evidence target, and establish a sanctioned non-production migration
actor. Only after those contracts pass deterministic fixture and sealed-package
qualification may HCP.MIGRATION.2 persistence begin.
