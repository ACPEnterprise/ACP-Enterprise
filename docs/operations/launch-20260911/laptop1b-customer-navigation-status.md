# Laptop1-B Customer navigation status

- Mission authority: `0c08f1e3634f38a7fb82970932dea5de7a4cf24f`
- Protected authority: `2d8709c895e60faf7cc0251d6c8ac82311013613`
- Lane: `work/customer-office-operating-acceptance-2`
- State: `PROTECTED_INTEGRATED_PREVIEW_ACCEPTANCE_PENDING`
- Prior Customer roster integration: PR #197 / `42a4f68087d76247269bd4c8388f556dd62a8b5c`
- Customer context/navigation integration: PR #205 / `e9377e72`
- Preferred-contact roster integration: PR #214 / `b22297c6`
- Independent acceptance coordination: OM2-C candidate `c2984e7` confirms the
  protected Customer/search routes enforce authentication, but classifies actual
  source-population and rendered operator acceptance as unverified until a current
  coherent Preview deployment and Migration admission packet exist.

## Implemented boundary

The Customer roster uses authoritative server-side search and total-aware
pagination. Customer detail exposes Contacts, Service Locations, bounded history,
and permission-scoped related operational records. Native created/updated dates
are labeled as native record dates rather than source acquisition dates.

Integrated navigation preserves selected Customer and Service Location when an
authorized office user opens Job creation. Generic Job creation searches the
complete admitted Customer population through the paginated search contract; it
does not silently select from the first 100 records.

The roster projects the authoritative preferred contact when present and supports
server-side name, Customer number, contact, phone, email, and address/location
search. Loading, empty, error, stale-page recovery, archived/restored state, and
responsive detail behavior are covered by the current product and deterministic
tests.

Company administrators receive the existing Migration readiness projection for
Customers, Contacts, and Locations, including source, admitted, held, exception,
unresolved, delta, stale state, and source-window end date. Held or source-only
records remain Migration evidence and are never selectable as native Customers.

## Coordination boundary

- Migration owns current source acquisition, disposition accounting, identity
  decisions, holds, and source-as-of evidence. Laptop1-B consumes only its
  authorized readiness projection.
- Laptop1-A owns Scheduling/Dispatch UI. Laptop1-B links into the integrated Job
  workflow with Customer/Location context and does not rewrite Scheduling state.
- Laptop1-A's existing-Job scheduling seam is authoritative through PR #217 /
  `2d8709c895e60faf7cc0251d6c8ac82311013613`. The navigation contract is:
  Customer detail → Create Job with
  the selected Customer and Location → `/jobs/{job_id}` → schedule using the Job's
  authoritative `branch_id`, `customer.id`, `service_location.id`, and
  `concurrency_version` → linked Appointment. The scheduling command requires
  both Job-manage and Scheduling-manage authority and must reject stale or
  mismatched context. Laptop1-B does not duplicate that implementation.
- Enterprise owns protected integration, Preview deployment, and authorized live
  Preview data writes.

Migration's September 12 GET-only operational packet is authoritative for the
current source gate: acquisition completed at `2026-09-12T16:49:00Z`, packet digest
`a2c427ccc8f99f33a2340fa84118f987d75f1997afc8f0c7cf7fc27123e87748`, and
decision digest `5070aa62a8a86bfbd1249588e86f1f08d29ae433803ba05fdf8ee04b234e9025`.
Relative to sealed SOURCE.4 it reports 55 added Customers and 63 added Locations.
Canonical admission remains false. Migration candidate `88b005cb` partitions the
1,389 legacy projections without changing their dispositions and qualifies the
provider-neutral current-overlay contract, but its concrete Preview adapter and
record packet are not deployed or invoked. The current-operation subset still has
22 open Jobs without provider Location identity and 13 held legacy current-open
Appointment projections; other cross-domain admission guards remain open. The
Customer UI must therefore continue to describe the native
population as admitted but partial and show the source readiness/as-of evidence; it
must not add source-only records to the selectable roster.

## Remaining acceptance

1. Enterprise deploys current protected authority. Preview health reported version
   `b5dff4b0203fe9a725a0ff844279876f410cba12` on September 12, 2026, one protected
   commit behind the preferred-contact integration.
2. Provide the lane an accepted authenticated Preview session without exposing an
   owner credential or weakening authentication.
3. After current deployment and authenticated access, verify roster
   pagination/search, source accounting, detail, and Customer-to-Job context.
4. After Migration accepts a successor admission packet, rerun the roster's total
   traversal and supported search matrix, then reconcile the displayed source
   counts and as-of date against that exact accepted digest. A partial source
   population remains partial.

The unauthenticated live checks are intentionally bounded: `/customers` renders
the application shell, `/backend-health` reports healthy PostgreSQL and Redis, and
the Customer API rejects the request with `401 Authentication required`. These
checks do not substitute for authenticated operator acceptance.

## September 12 qualification

- Isolated PostgreSQL zero-to-head migration plus focused Customer, Job,
  Operations, and Scheduling backend qualification: `127 passed` against PR #217
  authority.
- Focused Customer detail, roster, operations, and Job-context frontend
  qualification, including existing-Job scheduling: `44 passed` across six test
  files.
- Frontend ESLint and TypeScript/Vite production build: passed.
- `git diff --check`: passed.

Deterministic qualification now explicitly traverses page 1 to page 2 for both the
Customer roster and the Customer selector used during Job creation, asserting the
server query page changes. A first-page response or pagination label alone is not
accepted as completeness proof.

No real Customer mutation, Customer communication, Preview deployment, or
Production operation is authorized to this lane.
