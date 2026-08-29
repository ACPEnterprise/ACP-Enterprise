# Owner decision — HCP historical relevance cutoff

Effective August 26, 2026, `2023-01-01` changes HCP reconciliation requirements,
not source truth. Every HCP record remains eligible for immutable acquisition with
its original values, native identity, status, relationships and missing evidence.

## Three evidence layers

| Layer | Boundary | Requirement |
|---|---|---|
| `LEGACY_HISTORICAL_ARCHIVE` | source-operational date before 2023-01-01, unless it carries a current dependency | Acquire when HCP provides it. Missing historical controls, applications, mappings, economics, Note provenance and attachments are non-blocking and remain explicitly unreconciled. |
| `ENTERPRISE_ANALYTICAL_HISTORY` | 2023-01-01 through cutover | Primary plumbing-company analytical history. Acquire all reasonably available operational, workforce, lifecycle, Business Unit and financial evidence. Preserve exceptions and conflicts without cleansing. |
| `DAY_ONE_CUTOVER_STATE` | any record affecting current/open operations, balances or continuity | Highest evidence standard for Customers, Jobs, Appointments, Estimates, Invoices, Payments/AR, employees and required Notes/Attachments. Historical uncertainty cannot silently change a current balance. |

Day-1 dependency overrides age: a pre-2023 record carrying an open balance or
current operational dependency belongs to `DAY_ONE_CUTOVER_STATE` for disposition
while its original date remains unchanged.

Business Economics, Beacon, Luminary and LIA use 2023+ as the primary comparable
period. Legacy leak-detection history remains separately queryable and must not be
silently mixed into plumbing benchmarks, technician productivity, service mix or
job economics.

## Revised control decision

Additional 2017–2021 Payment controls are no longer required. The sealed 2022
Payment controls remain useful legacy/transition evidence and are retained. A
pre-2023 payment gap becomes blocking only when it affects a balance/open item
carried into 2023+ or cutover.

The protected Job discrepancy audit used GET-only API pages and did not start
HCP.SOURCE.4. The Job control's `Job #` is encoded as Excel text (`="value"`);
removing only that structural wrapper produces 4,816 control candidate matches.
Source bytes remain unchanged. The remaining 985 API Jobs are all provider
cancellation states:

| Relevance | API-only Jobs |
|---|---:|
| Legacy archive | 65 |
| 2023+ analytical history | 621 |
| Day-1/current-balance significance | 299 |

Of the Day-1 group, 296 report nonzero outstanding balances. These records are
not absent from HCP or excluded from acquisition—the API will acquire them. Their
absence from the native Job List control becomes explicit reconciliation evidence.
Legacy differences do not block. The 2023+ canceled Jobs remain reconciliation
exceptions. The Day-1 group must receive owner/accounting disposition before
cutover and cannot be assumed collectible, paid, void, or erroneous.

## Readiness

HCP.SOURCE.4 may start because the API supplies all 5,801 Jobs, controls are sealed,
the export exclusion is classified, and source acquisition can preserve every
assertion plus explicit missing evidence. HCP.SOURCE.4 must not treat the Job CSV
as a complete population control; it must reconcile 985 `SOURCE_API_MISSING_FROM_CONTROL`
results using relevance and retain the original cancellation/balance assertions.

This permission is readiness only; it does not authorize HCP.SOURCE.4 execution.
Open-work/accounting cutover remains blocked on the 299 Day-1 classifications,
including the 296 nonzero-balance assertions, plus previously required technician,
Note, attachment, appointment, AR and owner-disposition gates.
