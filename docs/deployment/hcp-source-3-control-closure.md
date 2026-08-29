# HCP.SOURCE.3 — control-export intake and residual-evidence closure

Status: code and protected intake are ready; the five owner-generated controls
have not yet been supplied. No HCP mutation or Enterprise import is authorized.

## Owner export instructions

Use the same HCP Admin account for all exports. Record the admin identity, HCP
Company, displayed filters/date range, company timezone, click time, email receipt
time, and original filename. Do not open and resave the files.

1. **Customer List:** HCP left navigation → **Customers** → clear any list filter
   or search → **Actions** → **Export** → confirm the admin email → **Send file**.
2. **Job List:** HCP left navigation → **Jobs** → clear every filter/search →
   **Edit columns** and include all available customer, Job identity/status,
   assigned employee, schedule, Business Unit, Notes, invoice, paid/due, and date
   columns → **Actions** → **Export** → **Send file**.
3. **Estimate List:** HCP left navigation → **Estimates** → clear every
   filter/search → **Edit columns** and include all available identity, status,
   outcome, employee, schedule, Business Unit, Notes, amount, and date columns →
   **Actions** → **Export** → **Send file**.
4. **Payments Summary and Payment Details:** HCP left navigation → **Reporting**
   → **Reports** → **Payments** → select the full available payment-date range →
   **Generate report**. Preserve both emailed files: Summary and Payment Details.

These paths and HCP's Admin-only rule are documented in
[Customer/Job exports](https://help.housecallpro.com/en/articles/6797101-how-to-import-export-jobs-and-customers),
[Job/Estimate List reporting](https://help.housecallpro.com/en/articles/8241575-job-estimate-list-reporting), and
[Payments export](https://help.housecallpro.com/en/articles/8028448-payments-export).
The Payments report filters on payment received date and produces both files.

Prefer one full-range Payments generation. If HCP rejects that range, use
calendar-date partitions in `America/New_York`. Record the exact inclusive start
and end dates displayed in HCP; the next partition starts on the calendar day
after the prior end. Never reuse a boundary date. Generate Summary and Details
for every identical partition, and seal the ordered ranges and per-file digests
into one aggregate manifest. Do not assume or invent a provider maximum range.

## Protected intake

Deliver original downloads directly to:

`~/.acp-enterprise/migration/housecall-pro/hcp-source-3-controls/incoming/`

The directory must be mode `0700`; every file becomes mode `0600`. It is outside
Git. Intake uses `hcp-control-export-intake/v1` and writes each artifact once. For
each CSV it verifies consistent columns and records source report identity,
timezone-aware extraction time, exact filters, computed row count and byte size,
raw SHA-256, exporting-admin evidence digest, ordered headers and header SHA-256,
protected artifact name, and Company identity digest. A manifest seals exactly
one Customer List, Job List, Estimate List, Payments Summary, and Payment Details;
duplicate filenames, missing controls, or cross-Company evidence fail closed.

Raw records, headers containing unexpected source data, and admin evidence remain
protected. Only manifest digests, classifications, and counts may enter a safe
operator report.

## API-to-control reconciliation

Reconciliation is a comparison, never a repair. Exact native IDs are primary:

| API | Control | Comparison evidence |
|---|---|---|
| Customers | Customer List | HCP Customer ID, embedded contact/address evidence and source-field digest |
| Jobs | Job List | HCP Job ID (not display number alone), customer/address IDs, status, dates and exact money |
| Estimates | Estimate List | HCP Estimate ID/number plus customer/address, outcome/status, dates and exact money |
| Invoice payment/refund containers | Payments Summary/Details | Job ID, Customer ID, invoice number/ID where present, payment timestamp, method and exact amount; Summary is aggregate-only |

Each deterministic result is `MATCHED`, `SOURCE_API_MISSING`,
`CONTROL_EXPORT_MISSING`, `CONFLICTING`, or `UNSUPPORTED_RELATIONSHIP`. A control
that lacks a native ID may use a multi-field comparison candidate but cannot
establish identity by name or number alone. Ambiguity becomes
`UNSUPPORTED_RELATIONSHIP`; original rows and API assertions remain unchanged.
Payment Summary reconciles partition totals by method and invoice count, not
individual identities.

## Residual closure decisions

### Notes

The actual Job API returned Note ID and content beneath its Job parent. It did not
return observed Note author or timestamp. Preserve the ID, parent, content and
missing provenance exactly. The Job List control may provide displayed Notes but
does not replace native Note identity. No broad historical Note export is needed.
For only Notes required by a later HCP.OPEN-WORK.1 selection, request HCP Support
provenance if author/time is unavailable; otherwise record those fields as missing
and apply the open-work rejection/disposition rule.

### Attachments

Authenticated detail expansion was accepted for Job and Customer attachments, but
the bounded records were empty; Estimate detail did not expose an observed
attachment field. Therefore metadata shape, stable URL/reference, availability,
content read, checksum, author and timestamps are not yet proven on populated
records. Do not download historical content. After HCP.OPEN-WORK.1 selects Jobs,
read only their required attachment metadata/content. Seal parent, provider ID or
URL identity, availability, byte size and SHA-256 without modifying content. If
HCP cannot return those facts, use the bounded Support request below.

### Payments and applications

Invoice list/detail and Job Invoice reads expose invoice native identity, Job
relationship, status, totals, due amounts/dates, paid time, and payment/refund
containers. The bounded sample did not prove populated payment fields. Payment
Details can independently supply Job ID, Customer ID, invoice number, payment
received timestamp, exact payment amount, method, and refunds as negative amounts;
Summary supplies totals/counts by method. Neither observed API nor documented
controls prove a distinct application ID, exact applied/unapplied split, or
processor reference in every case. Preserve absent fields as absent; never derive
`applied = payment` from an invoice status.

### Branch and Business Unit

HCP Business Unit is source job/estimate classification evidence. ACP Branch is
an Enterprise organizational/tenant boundary. They are not automatically
equivalent. The owner packet contains:

`SHA-256(Company ID + exact HCP Business Unit value) → nullable ACP Branch ID →
non-name evidence digests → unresolved/consistent/conflicting`.

Acceptable corroboration includes authoritative HCP location/Company ID,
operating address, service territory, employee roster/assignment pattern, and an
approved accounting location/class crosswalk. Matching labels alone are
insufficient. Until owner review, every candidate Branch remains null and
unresolved.

### Technician crosswalk

A narrow GET-only Employee pagination acquired all seven currently returned HCP
employees in one page. Every native ID was present and unique. The protected
owner-review packet retains exact native ID, source-reported active value (missing
when absent), safe identifying context, Company evidence, assignment and Business
Unit evidence when available, plus independent digests. It assigns zero Enterprise
employees. The owner must select an Enterprise Employee using HR/roster evidence;
name-only mapping, inactive-state inference, cross-Company mapping, duplicates,
and one target claimed by multiple HCP identities fail closed.

### HCP/QBO seam

`hcp-qbo-financial-assertions/v1` carries both provider assertions with native
entity/ID, field, original value and source digest. Equal values classify
`consistent`; unequal values classify `conflict`. For example, HCP `paid` and QBO
`open` remain two immutable assertions plus `CONFLICT`. Neither invoice is updated.
The seam can later feed Business Economics, Beacon, Luminary, LIA, and accounting
correction workflows by reference.

## Readiness and bounded Support request

Once the five controls pass protected intake, the complete source-faithful API
acquisition may proceed while truthfully recording unavailable evidence as
missing. Residual gaps have these impacts:

| Impact | Remaining condition |
|---|---|
| `BLOCKS_ACQUISITION` | Any missing/invalid control, Company mismatch, broken pagination, duplicate native identity conflict, or unprotected raw artifact |
| `BLOCKS_OPEN_WORK_CUTOVER` | Unreviewed technician mapping; missing in-flight disposition/freeze; required Note provenance without disposition; required attachment availability/content digest; financial continuity failure |
| `BLOCKS_RECONCILIATION` | Ambiguous API/control identities; unavailable payment applications/unapplied amounts; unresolved Branch crosswalk; HCP/QBO conflicts awaiting owner/accounting resolution |
| `NON_BLOCKING_MISSING_EVIDENCE` | Independent Contact identity, historical Note author/time, employee update time, non-open-work attachment detail, or a source-null optional relationship |

One Support request, sent only after reviewing the five controls:

> For All County's authorized migration, please provide only evidence not
> available in the Public API/native exports: (1) Note native ID, parent Job ID,
> created/updated timestamps and author employee ID for the owner-supplied list of
> Day-1 open-work Job IDs; (2) attachment native ID, parent, filename/type, stable
> reference, availability, size, timestamps, author and retrievable content or
> provider checksum for required attachments on that same Job list; (3) payment
> native/processor reference, invoice/Job relationship, amount, refund, applied
> and unapplied amounts, timestamp and method for rows in the supplied Payment
> Details manifests where those fields are absent; and (4) authoritative HCP
> location/branch IDs and their relationship to Company and Business Unit, if HCP
> maintains a distinct branch concept. Preserve source values; no formatting or
> correction is requested.

Exact next milestone after intake: **HCP.SOURCE.4 — full immutable HCP acquisition
and control reconciliation rehearsal**. It remains read-only and performs no
Enterprise import.
