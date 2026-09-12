# CSR.SCHEDULING.RECOVERY.ACCEPTANCE.1 qualification

## Authority and scope

- Protected starting authority: `8cf3bdbf0c814c4a45f2b189b061db556d1c704f`.
- Immutable prerequisite candidate: `7907a685481a268ac14269195c882839734451df`.
- This increment changes frontend recovery and qualification only. Scheduling, Jobs, Dispatch, Customer, and Migration remain the owners of source truth and mutation authority.

## Recovery contract

Every create/schedule/reschedule attempt now refreshes authoritative Appointment, Job, and Dispatch projections after success **or failure**. A Job scheduling attempt additionally refreshes the Job detail and technician projection. This lets a Job that was concurrently scheduled disappear from Needs Scheduling after server truth is returned, rather than remaining actionable from stale client state.

Operator outcomes remain distinct:

- `SUCCEEDED`: the API returned authoritative Appointment/Job evidence and the affected projections refreshed.
- `FAILED`: the server definitively rejected authorization or validation; the UI does not imply a persisted Appointment.
- `FAILED_REQUIRES_REFRESH`: stale version, capacity/technician conflict, changed lifecycle, or contradictory idempotency evidence; current projections refresh and stale confirmation closes.
- `UNKNOWN_REQUIRES_REFRESH`: the response was lost/timed out or the platform requires reconciliation. The exact request identity and payload are retained for a replay-safe retry only after the refresh settles.

Safe structured API failure codes remain operator-distinct: stale version, concurrency/capacity conflict, resource-state conflict, idempotency conflict, validation, and authorization. Internal details are never reflected.

## Idempotency and continuity

- Exact retry preserves both request ID and mutation payload.
- Editing an existing-Job scheduling intent produces a new request identity; it cannot contradict an earlier replay identity.
- Reschedule confirmation closes on error and is not blindly replayed because rescheduling is protected by authoritative Appointment version rather than the service-request identity.
- Successful booking links preserve the prior Scheduling URL, including view, date, Branch, technician, status, queue, search, and sort state.
- Query refresh makes records leave Needs Scheduling only when current Job/Appointment authority says they no longer belong there.

## Existing source boundary

The canonical source-contract limitation remains unchanged: current projections do not provide authoritative source freshness, source-observed timestamp/digest, Migration `HELD`/`SOURCE_ONLY`, or a requested service window distinct from the Appointment arrival window. The UI does not synthesize any of them.

## Qualification scenarios

Synthetic qualification covers success, definitive failure, response loss/timeout semantics, exact replay, stale Job version, capacity/technician conflict classification, authorization rejection, validation/inverted window, unassigned booking, partial Customer/Job context, unavailable APIs with bounded retry, and complete return-scope restoration. Existing responsive, keyboard, Month, queue, assignment, and calendar/Dispatch consistency suites remain in scope.

No schema, backend, source admission, Preview, Production, autonomous Dispatch, or Customer communication operation is included.
