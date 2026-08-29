# HCP.SOURCE.1 — source-faithful Housecall Pro acquisition foundation

Status: authorization-gated, fixture-validated design. This milestone does not
authorize or perform a real extraction, import, deployment, or source mutation.

## Authorization decision

Use a hybrid extraction: the Housecall Pro Public API is primary and native
exports are independent controls and gap-fillers. A Pro building a custom
integration uses an API key; OAuth is for verified integration partners. Public
API access is documented for MAX or XL plans. The extractor must issue only
documented `GET` requests, follow pagination, honor `429`/`RateLimit-Reset`, and
never register mutating webhooks or call create/update/delete endpoints.

The owner authorization gate is exact:

1. Confirm the ACP Housecall Pro subscription is MAX or XL and that the owner
   authorizes this one-company, read-only migration extraction.
2. In Housecall Pro, an owner/admin generates a dedicated API key for the custom
   integration following HCP's API-key instructions. If the account cannot create
   one, the owner asks HCP Support/API Developer Support to enable/confirm Public
   API access or provide a support export.
3. Deliver the key directly into the approved secret manager/runtime environment,
   never chat, Git, tickets, fixtures, command history, or logs. Record only the
   authorization evidence digest, key identifier/last four if HCP exposes it,
   authorizer, company/account identity, scope, creation time, and revocation plan.
4. Separately authorize the admin to generate the control exports listed below.
5. Only after a non-production connectivity review may an operator authorize a
   fixture-to-real extraction run. This milestone stops before that action.

## Provider coverage and fallback

Public documentation explicitly advertises customer, employee, job, job
attachment/link, and estimate access, and documents invoice list/job-invoice
endpoints. Job/estimate representations carry scheduling/dispatch concepts. The
first authorized schema-probe must inventory only `GET` operations from the live
HCP OpenAPI documentation and save its digest; an entity is never claimed merely
because a write endpoint or UI feature exists.

| Required evidence | Primary | Gap/fallback |
|---|---|---|
| Customers, contacts, service addresses | API customer representation | Admin Customer export; preserve embedded contacts/addresses as native child evidence |
| Employees/technicians | API employee representation | HCP Support export if list/detail omits stable IDs or branch facts |
| Jobs, lifecycle, assignments, appointments | API job list/detail and embedded relationships | Admin Job List export with all relevant columns; support export for appointment IDs/history |
| Estimates, outcome/acceptance, assignments | API estimate list/detail if present in authorized schema | Estimate List export with all relevant columns |
| Notes | API only where an official read operation/parent representation returns them | Job/Estimate exports for displayed notes; HCP Support export for stable note identity, author, timestamp, and parent |
| Attachments/artifacts | API job attachment/link reads; retain metadata and content hash only when authorized | HCP Support export for unsupported parents or missing metadata/content |
| Invoices | API invoice list and job-invoice reads | Job List/exported report financial columns; Support export for missing native identity/detail |
| Payments, applications, unapplied amounts | API only if the authorized schema exposes read operations and exact linkage | Payments Details export plus Summary control; Support export when application IDs/unapplied amounts are absent |
| Business unit/branch | Preserve fields embedded in API objects | Job and Estimate List exports with Business Unit; never infer branch |

Unknown/unsupported fields remain explicit gaps. In particular, a payment row
linked to a job/invoice is not proof of a distinct payment-application object or
unapplied amount. No relationship is synthesized.

Official references: [HCP Public API](https://docs.housecallpro.com/),
[Customer and Job exports](https://help.housecallpro.com/en/articles/6797101-how-to-import-export-jobs-and-customers),
[Job and Estimate List exports](https://help.housecallpro.com/en/articles/8241575-job-estimate-list-reporting), and
[Payments export](https://help.housecallpro.com/en/articles/8028448-payments-export).

## Immutable envelope and snapshot

`hcp-source-acquisition/v1` is implemented in
`backend/app/operational_migration/hcp_source_acquisition.py`. Every record stores
`provider=housecall_pro`, native entity and ID, status and unparsed provider
timestamps, timezone-aware acquisition time, extraction ID, explicit native
parent IDs, raw Company/Branch evidence, canonical SHA-256 digest, and the raw
provider mapping. Missing values stay missing. Raw pages/files and attachment
content are encrypted, access-controlled, retention-locked outside Git; Git may
contain deterministic fictional fixtures only.

A snapshot identity binds a unique extraction ID to source environment, requested
scope/filter, mechanism, request start/end, acquisition time, page and record
counts, and raw-artifact SHA-256. Each raw response page is written once before
parsing. Pagination order does not define record identity. A completed snapshot
is append-only; retries receive a new extraction ID and link operationally to the
superseded attempt. The close manifest sorts `(native_entity, native_id,
source_digest)`, rejects duplicate native identities with differing payloads,
records empty pages and errors, and cannot be called complete with an unfinished
page chain. API and exports are separate snapshots even when captured together.

## Separation and handoff

The three planes are independent:

1. **Source state:** immutable envelope and original HCP assertion.
2. **Cutover disposition:** HCP.OPEN-WORK.1 selection result and owner evidence.
3. **Enterprise operational state:** accepted Enterprise ID/state after an
   separately authorized transformation/import.

`MigrationHandoff` carries the envelope, transformation version, nullable cutover
disposition, nullable accepted Enterprise ID/state, and reconciliation state.
HCP.OPEN-WORK.1 consumes projections of envelopes only after acquisition and may
include/exclude/reject them; it cannot rewrite envelopes. Its existing Day-1 rules
remain authoritative for operational selection, not source retention.

## Cross-source reconciliation

Every comparison retains provider, native entity/ID, original value, source
digest, extraction ID, comparison rule/version, candidate keys, and outcome.
Candidate evidence keys are deterministic but never automatic merge decisions:

| Domain | Required candidate evidence (in addition to both native identities) |
|---|---|
| Customer | normalized email/phone plus service-address components or an existing reviewed crosswalk |
| Job | HCP job ID/number plus customer/location evidence, scheduled date, and exact amount where present |
| Estimate | estimate number plus customer/location and exact amount/date |
| Invoice | invoice number plus customer/job relation, currency, exact total, and date |
| Payment | provider transaction/reference plus invoice/job relation, exact amount/currency, and timestamp |
| Open balance | invoice candidate plus as-of time, currency, and exact source balance |
| Technician | reviewed crosswalk using provider employee ID and an authoritative enterprise employee ID |

Name-only matching is prohibited. Missing or ambiguous evidence yields
`unresolved`; multiple candidates are retained. HCP `paid` and QBO `open` become
two `SourceAssertion` records and a conflict record—never a selected winner.

## Minimal independent controls

For the final authorized extraction window retain only:

1. unfiltered Customer List export;
2. unfiltered Job List export with all available identity, lifecycle, assignment,
   scheduling, business-unit, notes, invoice, paid, and due columns;
3. unfiltered Estimate List export with all available status/outcome, assignment,
   date, business-unit, and financial columns;
4. Payments Summary and Payment Details exports for the complete available date
   range (the report filters by payment date).

Record UI filter/date settings, generation/download timestamps, admin identity,
row counts, filenames, byte sizes, and SHA-256. These controls prove counts/totals
and expose gaps; they do not overwrite API evidence. Request a one-time HCP
Support export only for required stable notes, appointments, artifacts, payment
applications/unapplied amounts, or branch evidence that the authorized API/schema
probe and four native controls cannot supply. No recurring historical manual
exports are required.

## Intelligence evidence handoff

Later consumers receive references, not rewritten truth: Business Economics gets
versioned monetary assertions and inconsistency records; Beacon gets immutable
source/change signals; Luminary gets provenance, comparison rules, candidates and
conflicts for explanations/recommendations; LIA gets the same evidence plus owner
disposition and resolution audit links. None may mutate the envelope or fabricate
identity, and none is implemented by HCP.SOURCE.1.

## Next gate

Next milestone: **HCP.SOURCE.2 — owner-authorized read-only schema probe and
fixture-to-provider extractor qualification**. It begins only after the owner
completes the API-key/support gate above. It must still perform no Enterprise
import and touch neither Preview nor Production.
