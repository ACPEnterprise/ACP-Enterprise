# HCP.MIGRATION.2B persistence admission

HCP.MIGRATION.2B closes the persistence blockers found by the first real
MIGRATION.2 preflight. It adds infrastructure only; it does not create a master
run or persist HCP business records.

## Customer admission

The provider-native Customer ID is the admission identity. Shared names,
emails, phones, or addresses remain deterministic review signals but never
merge Customers or block admission. Actual duplicate provider IDs, changed
authoritative evidence, and scope conflicts still fail closed.

Contact and Service Location failures are child exceptions. They no longer
reject an otherwise valid parent Customer. All valid locations in a
multi-location aggregate follow the Customer through the sanctioned import
service; exceptional children remain staged and countable.

The sealed Customer control now qualifies as follows:

- 5,248 source rows and 5,248 admissible parent Customers
- zero parent transformation rejections or source-ID duplicates
- 4,123 supported Contacts
- 3,735 supported Service Locations and 1,555 billing addresses
- 1,106 child exceptions affecting 1,065 Customers
- 136 multi-location parent Customers
- 2,452 identities in similarity-only review evidence

## Durable evidence

Alembic revision `a4c8e0f2b735` adds four Company/Branch-isolated contracts:

- `hcp_customer_source_lineage` binds native Customer identity, SOURCE.4 and
  transformation digests, timestamps/context, disposition, and master run.
- `hcp_employee_source_crosswalks` preserves versioned owner disposition and
  native Employee identity. Excluded non-human identities cannot reference an
  Enterprise Employee, and one target Employee cannot receive multiple HCP
  identities.
- `hcp_migration_holds` represents `HELD` and later `RELEASED` evidence as
  append-only versions. Holds have no operational effect and cannot establish
  accepted financial truth.
- `hcp_migration_master_runs` binds package/collection digests, exact contracts,
  five owner receipts, actor, tenant scope, schema head, baseline and all
  reconciliation count classes under one deterministic input digest and UUID.

Customer lineage, Employee crosswalk, and hold evidence reject update/delete.
Exact replay returns the existing evidence; changed evidence for the same
native identity fails closed. The master run remains mutable only through its
controlled lifecycle so progress, reconciliation, replay, and resume state can
be attested at completion.

## Release boundary

The isolated rehearsal target contains the new empty infrastructure tables and
remains at zero real HCP business rows. The one pre-existing synthetic unlinked
Estimate qualification row remains explicitly marked synthetic. Actual
MIGRATION.2 execution still requires separate owner approval.
