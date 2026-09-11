# Laptop1-B Customer navigation status

- Mission authority: `0c08f1e3634f38a7fb82970932dea5de7a4cf24f`
- Product base: `42a4f68087d76247269bd4c8388f556dd62a8b5c`
- Lane: `work/customer-office-navigation-acceptance-1`
- State: `QUALIFICATION_IN_PROGRESS`
- Prior Customer roster integration: PR #197 / `42a4f68087d76247269bd4c8388f556dd62a8b5c`

## Implemented boundary

The Customer roster uses authoritative server-side search and total-aware
pagination. Customer detail exposes Contacts, Service Locations, bounded history,
and permission-scoped related operational records. Native created/updated dates
are labeled as native record dates rather than source acquisition dates.

The follow-on navigation preserves selected Customer and Service Location when an
authorized office user opens Job creation. Generic Job creation searches the
complete admitted Customer population through the paginated search contract; it
does not silently select from the first 100 records.

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
- Enterprise owns protected integration, Preview deployment, and authorized live
  Preview data writes.

## Remaining acceptance

1. Finish full frontend regression and changed-boundary security checks.
2. Push the qualified continuation commit and hand it to Enterprise.
3. After protected integration and Preview deployment, verify authenticated roster
   pagination/search, source accounting, detail, and Customer-to-Job context.
4. Reconcile displayed source counts and as-of date against Migration's final
   current-source packet; a partial source population remains partial.

No real Customer mutation, Customer communication, Preview deployment, or
Production operation is authorized to this lane.
