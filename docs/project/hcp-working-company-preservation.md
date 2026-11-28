# HCP Working Company Preservation and Promotion

Status: preservation checkpoint only. No live cutover is authorized by this document.

## Preserved checkpoint

- Application commit: `010dc23256ba921c7c5dec70ad6d2cdfce07e121`
- Checkpoint tag: `checkpoint/hcp-migration-working-20261127-010dc232`
- Runtime: `http://127.0.0.1:18187/`
- Database: `acp_application_acceptance`
- Database backup: `/Users/michaelfouse/ReleaseEvidence/hcp-migration-preservation-20261127/migration-company-acp_application_acceptance-20261127.dump`
- Backup SHA-256: `271e7e1a29590db4c98734fe050fe699fd5c947c8e248d10ddd6ee6250bbda37`
- Preservation manifest: `/Users/michaelfouse/ReleaseEvidence/hcp-migration-preservation-20261127/preservation-manifest.json`
- Preservation manifest SHA-256: `443e2e057af385ed5808903acd442b07203008c48d622aea0ca7487699f39e61`

The original All County company and the partial legacy migration company remain separate and unchanged. The recovered source package and attachment custody remain at their existing protected paths and are mounted read-only.

## Qualified working-company clone

The first independent promotion clone is running for owner acceptance:

- URL: `http://127.0.0.1:18188/`
- Company: `All County Plumbing & Leak`
- Company ID: `f8b460b4-e08c-4437-abc0-f8fd17ad8966`
- Working-company manifest: `/Users/michaelfouse/ReleaseEvidence/hcp-migration-preservation-20261127/all-county-working-company-manifest.json`
- Working-company manifest SHA-256: `ed5abe06f6cd47be238bdb0eae9c488c30733c972cbc760dce1ab62f0e8b0642`

This clone has its own PostgreSQL volume and application containers. Its database was restored from the preserved dump and its company display name was changed only inside the clone. The migration runtime on port 18187 remains available as the untouched preservation source.

## Simplest reliable promotion path

1. Keep the recovered migration company as the canonical historical-data foundation; do not repair or overwrite the old partially populated company.
2. Clone the preserved application checkpoint and restore the verified database dump into a new isolated target.
3. Mount the exact source package and attachment custody read-only, then verify source-manifest and media-manifest digests against the preservation manifest.
4. Run authenticated owner acceptance on customer search, Hammer Haag history, job detail, invoices, notes, and media before any operational write capability is enabled.
5. Register the independently migrated QuickBooks dataset as a separate read-only source. Do not promote it into native accounting until company binding, totals, and reconciliation exceptions are independently accepted.
6. Create a fresh governed release candidate only after backup, restore, migration, browser acceptance, and rollback evidence are bound to the exact application and configuration identities.
7. Perform any future cutover as a reversible, separately authorized tenant/environment transition. No source-system write, financial posting, payroll submission, notification, or dispatch activation is implied by this preservation checkpoint.

## Modules that can be enabled safely first

Enable behind the migration-company administrator and read-only historical permissions:

- Unified customer search and customer profiles.
- Service locations and source-backed customer timelines.
- Historical job and appointment detail, sorted by scheduled service date.
- Read-only estimates, invoice detail, payment evidence, and explicit source discrepancies.
- Read-only recovered photographs and documents through authenticated media delivery.

Keep disabled until separately qualified and authorized:

- QuickBooks OAuth, posting, banking, payroll, and native ledger admission.
- Live dispatch assignment, technician work execution, timeclock writes, and payroll submission.
- Customer notifications and external invitations.
- Destructive edits or deletion of historical records.

Native operational modules may be enabled incrementally only after each has a tenant-scoped permission review, backup/rollback evidence, and authenticated browser acceptance. Historical records remain read-only regardless of which native module is enabled.

## Preserved source methodology

The repeatable onboarding method is: acquire only through approved read-only custody, seal source and attachment manifests, project source history without fabricating relationships, preserve unresolved records as explicit exceptions, import or register by exact provider identity, verify idempotency, and perform record-level browser acceptance. Large import controls remain administrative; ordinary customer screens show the unified result rather than migration mechanics.

Owner-review exceptions remain open and preserved: 154 invoice association exceptions and 40 attachment exceptions. No exception was silently excluded or deleted.
