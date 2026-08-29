# HCP.SOURCE.2 — read-only extractor qualification

Probe date: August 26, 2026. Result: **qualified for the proven API surfaces;
full source-faithful acquisition is not yet ready because required control and
gap exports have not been supplied.** No Enterprise import occurred.

## Authorization and security evidence

The protected configuration existed outside Git, was exactly mode `0600`, had a
non-empty `HOUSECALL_PRO_API_KEY`, and used the approved
`https://api.housecallpro.com` base. `GET /company` returned `200`; the company
name safely matched All County and a native company ID was present. No credential,
record value, or raw response entered terminal output or Git. Raw responses are
mode `0600` beneath the mode `0700` protected HCP migration evidence directory.

All provider calls were `GET`. No write-capable client operation was implemented.
Official HCP documentation confirms Pro API-key authentication and the public API
surface: [HCP API](https://docs.housecallpro.com/) and
[API overview](https://help.housecallpro.com/en/articles/8505035-api-overview).

## Actual capability matrix

These classifications combine authenticated responses with actual fields in the
bounded sample; they are not inferred from UI features.

| Required domain | Classification | Actual evidence |
|---|---|---|
| Customers | `API_AVAILABLE` | list/detail `200`; native ID and create/update timestamps |
| Contacts/embedded contacts | `API_PARTIAL` | email and phone fields embedded; no independent contact identity/history |
| Service locations/addresses | `API_AVAILABLE` | embedded address objects have native IDs and address components |
| Employees/technicians | `API_AVAILABLE` | list `200`; native ID, role, Company ID, created timestamp |
| Jobs | `API_AVAILABLE` | list/detail `200`; native ID and timestamps |
| Job lifecycle/status | `API_AVAILABLE` | `work_status`, cancellation/deletion/lock and work timestamps |
| Technician assignments | `API_AVAILABLE` | assigned employee objects with native employee IDs |
| Appointments | `API_AVAILABLE` | job appointment `GET` returned native appointment ID, times, arrival window and dispatched employee IDs |
| Estimates | `API_AVAILABLE` | list/detail `200`; native ID, status, timestamps, options and outcome/approval evidence |
| Notes | `API_PARTIAL` | Job representation returns note ID/content; author and note timestamp absent in observed schema |
| Attachments/artifact metadata | `API_PARTIAL` | documented detail expansion was accepted; bounded job/customer sample was empty, so populated metadata/content retrieval remains unqualified; estimate expansion returned no attachment field |
| Invoices | `API_AVAILABLE` | global list, job relationship list, and `/api/invoices/{id}` detail returned `200` |
| Payments | `API_PARTIAL` | invoice payment/refund containers exist; bounded invoice sample did not prove populated payment identity/detail |
| Payment applications | `SUPPORT_EXPORT_REQUIRED` | no distinct application identity/linkage proven |
| Unapplied amounts | `SUPPORT_EXPORT_REQUIRED` | no field or relationship proven |
| Business unit | `API_AVAILABLE` | `job_fields.business_unit` and `estimate_fields.business_unit` preserved |
| Branch | `API_PARTIAL` | Company ID/name present; no distinct branch identity proven |
| Native IDs | `API_AVAILABLE` | present on all five sampled top-level collections and observed child domains |
| Timestamps | `API_PARTIAL` | strong Job/Customer/Estimate coverage; Employee lacks observed update time and Invoice uses financial dates rather than create/update fields |
| Relationships | `API_PARTIAL` | customer/address/employee/job/estimate/invoice relationships exist; contact, note provenance, artifact, application and branch relationships remain incomplete |

`NOT_APPLICABLE` was not assigned to any requested source domain.

## Bounded qualification evidence

Two records each were acquired from Customers, Employees, Jobs, Estimates, and
Invoices. One detail request was made for Customer, Job, Estimate, Invoice, Job
Appointments, and Job Invoices. Raw record values were never printed.

All collections returned `page`, `page_size`, `total_items`, and `total_pages`.
Repeating Jobs page 1 produced the identical byte digest; Jobs page 2 returned no
native-ID overlap with page 1. All 10 collection records sealed successfully into
`hcp-source-acquisition/v1` envelopes with native IDs and stable SHA-256 digests.
Status and timestamps remained exactly as returned. Missing fields stayed missing.

The production implementation adds:

- an exact mode/base/required-secret gate with redacted credential representation;
- a transport exposing only `GET` and accepting only relative paths on the fixed
  approved host;
- protected mode-`0700` evidence storage and mode-`0600`, create-once artifacts;
- strict four-field pagination parsing;
- native-ID presence requirements and rejection of conflicting duplicate digests;
- source-faithful envelope sealing with explicit relationships only.

It performs no normalization, conflict resolution, QBO comparison, cutover
selection, or import.

## Remaining controls and gaps

Retain all five HCP.SOURCE.1 native controls. None can yet be safely eliminated:

1. **Customer List** — independent total and embedded-contact/address control.
2. **Job List** — lifecycle, assignments, notes, financial/open-work and Business
   Unit completeness control.
3. **Estimate List** — estimate status/outcome and Business Unit control.
4. **Payments Summary** — independent aggregate financial control.
5. **Payment Details** — payment identity/linkage/time control where API evidence
   was not proven populated.

[HCP documents Customer/Job exports](https://help.housecallpro.com/en/articles/6797101-how-to-import-export-jobs-and-customers),
[Job/Estimate List exports](https://help.housecallpro.com/en/articles/8241575-job-estimate-list-reporting), and
[Payments Summary/Details](https://help.housecallpro.com/en/articles/8028448-payments-export).

Request one bounded HCP Support export for stable note author/timestamps, populated
attachment metadata/content availability, distinct payment-application identity,
unapplied amounts, and branch identity only where the five controls do not contain
them. This is a gap request, not a broad historical manual-export program.

## Full-acquisition readiness gate

Before full acquisition:

- obtain and hash the five control exports;
- qualify a populated attachment and populated payment/refund example, or record
  the corresponding Support export contract;
- obtain note author/timestamp provenance;
- determine whether All County has distinct HCP branch/location identities and,
  if so, obtain their authoritative IDs;
- prepare the reviewed HCP employee-ID to Enterprise employee-ID crosswalk;
- bind nested customer, address, assigned employee, appointment, estimate and
  invoice relationships into explicit envelopes without flattening source data;
- run HCP.OPEN-WORK.1 only after the immutable acquisition, with owner dispositions
  and the exact freeze time kept separate.

Exact next milestone: **HCP.SOURCE.3 — control-export intake and residual-evidence
closure**. Full HCP acquisition remains gated until HCP.SOURCE.3 closes or formally
dispositions the gaps above.
