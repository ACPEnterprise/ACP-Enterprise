# Laptop1-B Customer navigation status

- Mission authority: `0c08f1e3634f38a7fb82970932dea5de7a4cf24f`
- Protected authority: `b22297c65165280a761860198dc05441df4a4312`
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
- Laptop1-A candidate `91e3cf4f3e473a58b90869cfbce68b61baac5f03`
  (`work/job-existing-scheduling-ui-1`) supplies the remaining existing-Job
  scheduling seam. The navigation contract is: Customer detail → Create Job with
  the selected Customer and Location → `/jobs/{job_id}` → schedule using the Job's
  authoritative `branch_id`, `customer.id`, `service_location.id`, and
  `concurrency_version` → linked Appointment. The scheduling command requires
  both Job-manage and Scheduling-manage authority and must reject stale or
  mismatched context. Laptop1-B does not duplicate that implementation.
- Enterprise owns protected integration, Preview deployment, and authorized live
  Preview data writes.

## Remaining acceptance

1. Enterprise deploys current protected authority. Preview health reported version
   `b5dff4b0203fe9a725a0ff844279876f410cba12` on September 12, 2026, one protected
   commit behind the preferred-contact integration.
2. Provide the lane an accepted authenticated Preview session without exposing an
   owner credential or weakening authentication.
3. After current deployment and authenticated access, verify roster
   pagination/search, source accounting, detail, and Customer-to-Job context.
4. Reconcile displayed source counts and as-of date against Migration's final
   current-source packet; a partial source population remains partial.

The unauthenticated live checks are intentionally bounded: `/customers` renders
the application shell, `/backend-health` reports healthy PostgreSQL and Redis, and
the Customer API rejects the request with `401 Authentication required`. These
checks do not substitute for authenticated operator acceptance.

## September 12 qualification

- Isolated PostgreSQL zero-to-head migration plus focused Customer, Job, and
  Scheduling backend qualification: `122 passed`.
- Focused Customer detail, roster, operations, and Job-context frontend
  qualification: `36 passed` across four test files.
- Frontend ESLint and TypeScript/Vite production build: passed.
- `git diff --check`: passed.

Deterministic qualification now explicitly traverses page 1 to page 2 for both the
Customer roster and the Customer selector used during Job creation, asserting the
server query page changes. A first-page response or pagination label alone is not
accepted as completeness proof.

No real Customer mutation, Customer communication, Preview deployment, or
Production operation is authorized to this lane.
