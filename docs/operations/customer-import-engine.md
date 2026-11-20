# Customer import engine

The TwelveHats customer import boundary admits a customer roster without
requiring historical jobs, estimates, invoices, payments, or accounting data to
be available. Those domains have separate admission contracts and can be
reconciled later.

## Supported flow

Every provider or file adapter must produce the same reviewed customer output:

1. Read and validate the source artifact and schema.
2. Persist the source artifact, source rows, mapped candidates, evidence, and
   child exceptions in tenant and Branch scope.
3. Produce a reviewed output with a source digest, schema version,
   transformation digest, row-level identity, and reconciliation counts.
4. Admit only the explicit approved source-identity boundary.
5. Record a source identity for every admitted customer and preserve the native
   customer UUID.
6. Return a durable reconciliation report and audit evidence.

The HCP API adapter and HCP CSV adapter use this same reviewed boundary. The
recovered All County export is a 450-column CSV; adapters may preserve
additional columns without changing the canonical customer row contract. A
workbook is not treated as a different identity system: it must be converted
by an approved adapter into the same reviewed row contract before admission.

## Source identity namespaces

Source identity is the tuple `(tenant, Branch, source system, source record)`.
The two HCP namespaces are intentionally distinct:

- `housecall_pro` is the legacy customer-population reconciliation namespace.
- `housecall_pro_source4` is the sealed SOURCE.4 operational namespace.

They must never be normalized into one string merely because both originate
from HCP. A SOURCE.4 record may be bound to an existing native customer only
through qualified successor evidence. The binding preserves both the original
legacy identity and the SOURCE.4 identity; it does not replace the customer or
create a duplicate.

## Name projection and native changes

Customer display data is projected from the authoritative reviewed source
payload. For a person, the source first and last names form the display name;
for a business, the authoritative company name is used. A stale tenant label
or an old projection must not become the customer's display name.

An update carrying a source timestamp older than the native customer's
`updated_at` is held as `newer native Customer state is authoritative`. It does
not overwrite the native change. The hold is durable and reviewable.

## Idempotency and replay

Replay is keyed by tenant-scoped source identity and immutable source/staging
evidence. Replaying the same file or API page:

- returns duplicate/replay dispositions for already-bound identities;
- creates no second customer, contact, location, event, or audit truth;
- preserves the original native customer UUID and source binding; and
- never silently rewrites a newer native customer change.

Changed source evidence must produce a new reviewed artifact or a typed
conflict. It must not be accepted as an accidental replay.

## Ambiguous matches

Name, phone, email, and address similarity is evidence for review, not an
identity merge by itself. An ambiguous or duplicate candidate is placed in an
explicit `HELD`/quarantine disposition with its source row and evidence digest.
It does not block unrelated exact-provider rows from admission. A held row can
be retried after an authorized human resolves the identity without changing
the source record or creating a duplicate.

## Customer-only admission boundary

Customer-roster admission is intentionally independent from operational and
financial admission. A customer import may complete while the following remain
waiting, held, or unavailable:

- historical jobs and appointments;
- estimates and invoices;
- payments and accounting postings; and
- payroll or other financial evidence.

Operational child records may be admitted only after their exact customer and
location parents and their own lifecycle evidence pass validation. Missing or
invalid child evidence is held; it does not roll back unrelated qualified
customer admission.

## Reconciliation report

Every review/import reports at least:

- source rows discovered and schema validation result;
- accepted, rejected, duplicate, and held rows;
- source identities and source-row digests;
- customers, contacts, and locations proposed/admitted;
- exact bindings versus successor matches;
- ambiguous/held reasons and evidence references;
- replayed identities and created native IDs; and
- child domains still pending independently.

The normal customer-population API exposes the refresh and clean-majority
boundaries at:

- `POST /api/v1/customer-migration/population/refresh`
- `POST /api/v1/customer-migration/population/admit-clean-majority`

Both are tenant/Branch and permission scoped. The API must not report a source
row as admitted when it was merely staged or when its identity remains held.

## Regression contract

The backend regression suite covers:

- `housecall_pro` versus `housecall_pro_source4` namespace separation;
- correct person/company name projection instead of the stale tenant name;
- replay of the same file without duplicate customers or source identities;
- preservation of newer native customer changes;
- durable ambiguous-match holds with safe rows continuing; and
- customer-roster admission without jobs or accounting records.

Focused checks:

```text
pytest backend/tests/operational_migration/test_hcp_current_overlay.py
pytest backend/tests/customer_migration/test_adapter_import.py
pytest backend/tests/customer_migration/test_population_reconciliation.py
```

The importer contract tests exercise deterministic CSV/XLSX staging, mapping
validation, replay, and namespace separation. The existing adapter tests
exercise persisted staging, source identities, native customers, contacts,
locations, events, audits, and replay dispositions. The population test
exercises the FastAPI route and then reads the persisted customer and
source-identity rows. The SOURCE.4 binding test reads both the legacy and
`housecall_pro_source4` identities after alias matching and verifies that the
same native customer has two distinct, durable source identities.

The local laptop test environment currently has no resolvable `postgres`
hostname, so these database/API tests can be collected but cannot be reported
as executed locally until a sanctioned PostgreSQL test database is available.
The in-memory overlay tests remain useful for structural fail-closed behavior,
but they are not a substitute for the persisted importer and API tests.

