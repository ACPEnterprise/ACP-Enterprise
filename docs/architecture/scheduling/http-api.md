# Scheduling HTTP API

## Purpose

The Scheduling HTTP API exposes the approved Appointment creation, cancellation,
and rescheduling workflows without moving business rules into FastAPI. It follows
the canonical [request transaction contract](../request-transaction-contract.md)
and the Scheduling [Domain Architecture Brief](domain-architecture-brief.md).

## Authorization

All endpoints require authentication, an active Company and Membership, and
authorized Branch access. Appointment detail and calendar queries require
`COMPANY_SCHEDULING_READ`; mutations require `COMPANY_SCHEDULING_MANAGE`. Neither
permission implies the other or grants Company administration, Customer mutation,
Dispatch, Job, or financial capability.

New installations receive and assign the permission through Platform Bootstrap.
Existing initialized installations must first run the explicit, idempotent catalog
synchronization command:

```bash
python -m app.platform.permissions.sync_catalog
```

Synchronization inserts missing canonical Permission records only. It does not
modify existing Permission records, delete non-canonical records, or grant the new
permission to any existing Role. An administrator holding
`COMPANY_PERMISSION_MANAGE` then assigns the synchronized Permission through the
existing `PUT /api/v1/company-admin/roles/{role_id}/permissions/{permission_id}`
endpoint, using the Permission identifier reported by the command and the Role
identifier returned by `GET /api/v1/company-admin/roles`. That assignment increments
affected Users' authorization versions, so they must reauthenticate before the new
grant becomes effective. No schema migration is required.

For an existing preview installation, the controlled rollout order is: back up the
database, run the synchronization command once in the backend runtime, authenticate
as an administrator with `COMPANY_PERMISSION_MANAGE`, retrieve the intended Role,
assign only the reported Scheduling Permission identifier, and then reauthenticate.
The synchronization command is safe to repeat and never performs the Role assignment.

Cross-Company and inaccessible Branch, Customer, Service Location, and Appointment
references are concealed with the same generic `404` response.

## Endpoints

### `GET /api/v1/scheduling/appointments/{appointment_id}`

Returns a tenant- and Branch-concealed Appointment detail through the shared
Scheduling Query Engine.

### `GET /api/v1/scheduling/appointments`

Returns a bounded, paginated calendar query. `start_at` and `end_at` are required
timezone-aware boundaries. Optional filters cover Branch, lifecycle status, Customer,
and Service Location. Results use half-open overlap semantics and deterministic
ordering. See [Scheduling Query Engine](query-engine.md).

### `POST /api/v1/scheduling/appointments`

Creates a scheduled Appointment and capacity reservation. The request contains the
Branch, Customer, Service Location, timezone-aware arrival window, positive expected
duration, and positive Decimal capacity requirement. The response is `201 Created`.

Creation transactionally stages authoritative `appointment.created` and legacy
`appointment.booked` events. The latter is only an Analytics compatibility
projection for existing Mission Control calculations; both share the Appointment,
Company, transaction, and occurrence timestamp.

Creation currently has no durable request-idempotency key. A client must not blindly
retry after an ambiguous timeout: if the first transaction committed, a retry can
create a second Appointment.

### `POST /api/v1/scheduling/appointments/{appointment_id}/cancel`

Cancels an Appointment using the caller's expected concurrency version and one of:

- `customer_request`
- `duplicate_appointment`
- `scheduling_conflict`
- `service_unavailable`

An identical retry is an idempotent success even when it carries the version used
by the original successful cancellation. A retry with a different reason conflicts.
Capacity is released and `appointment.cancelled` is staged exactly once.

### `POST /api/v1/scheduling/appointments/{appointment_id}/reschedule`

Moves an Appointment's arrival window and capacity reservation within its existing
Branch. The request includes the expected concurrency version, replacement
timezone-aware window, positive duration, Decimal capacity, and one of:

- `customer_request`
- `operational_adjustment`
- `scheduling_conflict`
- `weather`

Cross-Branch rescheduling is not supported. Successful rescheduling increments the
version and reschedule count and stages `appointment.rescheduled`.

## Response contract

All endpoints return the same immutable typed Appointment representation:

- identifiers and Appointment number
- Company, Branch, Customer, and Service Location identifiers
- lifecycle status
- nullable arrival window and expected duration (draft states may omit them)
- nullable persisted reservation capacity (a draft may have no reservation)
- concurrency version and reschedule count
- cancellation and rescheduling timestamps where applicable
- creation and update timestamps

Callers must retain `concurrency_version` and submit it with later mutations.

## Error contract

- `401`: authentication is absent or invalid.
- `403`: the authenticated identity lacks `COMPANY_SCHEDULING_MANAGE`.
- `404`: a tenant-concealed Scheduling or referenced resource is unavailable.
- `409`: stale version, lifecycle conflict, calendar closure, or insufficient
  capacity.
- `422`: malformed transport data or a structurally valid request rejected by
  Scheduling domain validation.

Responses never expose internal exception text, SQL details, or tenant identifiers.

## Transaction ownership

Authentication and authorization use the request security session and produce an
immutable `AuthorizationContext`. The router receives a distinct application
session and invokes `SchedulingService`. The service alone opens the mutation
transaction; repositories never commit or roll back. Appointment persistence,
capacity changes, number allocation, and Business Events commit or roll back as one
unit.
