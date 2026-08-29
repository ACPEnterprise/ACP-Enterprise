# HCP.MIGRATION.2A persistence foundation

HCP.MIGRATION.2A removes the three architectural blockers found by the first
MIGRATION.2 release check. It does not persist acquired HCP business records.

## Registered SOURCE.4 layouts

The `housecall_pro` operational pipeline registers exact, versioned contracts
for the acquired SOURCE.4 layouts:

| Entity | Version |
| --- | --- |
| Job | `hcp_source4_jobs_api_v1` |
| Appointment | `hcp_source4_job_appointments_api_v1` |
| Estimate | `hcp_source4_estimate_options_api_v1` |
| Invoice | `hcp_source4_invoices_api_v1` |
| Payment assertion | `hcp_source4_invoice_payments_api_v1` |
| Job Note | `hcp_source4_job_notes_partial_api_v1` |

The contracts require the exact acquired columns, validate nested provider
objects, retain native IDs and package/source/disposition digests, and preserve
only explicit relationships. Unknown versions remain rejected as
`unsupported_export_version`; registered versions with changed columns are
rejected as `changed_layout`.

No Attachment contract is registered. The authoritative state remains
`ACQUISITION_INCOMPLETE_NOT_AUTHORITATIVE_ABSENCE`. Note provenance remains
partial, Payment records remain assertions with application evidence
unavailable, and neither becomes accepted accounting truth through these
transformations.

## Rehearsal service actor

The isolated loopback target contains a credential-less service identity
created through Company, Membership, BranchAccess, Role, and Permission domain
models. It has one permission only:
`COMPANY_MIGRATION_REHEARSAL_EXECUTE`. The initializer validates the approved
`migration_rehearsal` target before database use and uses the platform bootstrap
advisory lock for deterministic initialization.

The sanctioned scope is:

- Company `3ddf07ce-0f44-4b67-a40f-fb0ec41bb7cd`
- Branch `887f413a-70dc-4ab1-98aa-8e84f4e7efd0`
- service User `c427ebd1-7583-4c0d-9c54-55a0c1214174`
- Membership `e5d176ae-44fa-45c5-b543-c93f2e1656e2`
- Role `15d750e2-b014-4142-8ffd-1e45078e247a`

The service address uses the non-routable `.invalid` domain. No credential,
interactive login, administrator role, Preview identity, or Production
identity exists for this actor.

## Unlinked Estimate evidence

Alembic revision `f3b7d9e1a624` adds the immutable,
Company/Branch-isolated `operational_migration_unlinked_estimate_evidence`
table. It preserves the authorized `UNLINKED_NON_OPERATIONAL_ESTIMATE`
assertion without weakening the operational Estimate aggregate's required Job
parent.

The evidence row retains native Estimate, Customer, and Service Location IDs
where authoritative; source/package/owner/evidence digests; source status,
timestamps, option evidence, and context; and an explicit absent Job
relationship. Database constraints keep all operational effects and accounting
truth disabled. An immutable trigger rejects updates and deletes. Idempotent
replay accepts the same native ID plus digest and rejects conflicting evidence.
Later promotion requires a separate controlled reconciliation process.

Only one synthetic qualification row is present after this milestone. No real
HCP business candidate was persisted.

## Release boundary

The release gate requires verified owner receipts, verified SOURCE.4 package,
qualified transformations, the scoped actor, the evidence target, and zero real
HCP business rows. Passing this gate makes HCP.MIGRATION.2 mechanically ready;
it does not authorize its execution.
