# Scheduling Query Engine

## Purpose

The Scheduling Query Engine is the authoritative Appointment read boundary for the
Calendar API and future Dispatch, Mission Control, mobile, timeline, AI, Analytics,
and reporting consumers. Consumers reuse query intent and service orchestration rather
than recreating tenant, Branch, overlap, filtering, or ordering logic.

## Architecture

```text
HTTP or internal consumer
→ immutable AuthorizationContext
→ SchedulingQueryService
→ immutable AppointmentQuery
→ SchedulingRepository SQL
→ PostgreSQL
→ immutable AppointmentQueryRecord DTOs
```

`AppointmentQuery` carries Company scope, authorized Branch identifiers, an optional
Branch, a required bounded time range, optional lifecycle, Customer, and Service
Location filters, and pagination. It contains no SQL. The service validates scope and
query policy. The repository applies every Company and Branch predicate in SQL,
performs a single outer join for capacity, and returns DTOs rather than ORM entities.
Reads use the application session but open no mutation transaction and acquire no row
locks.

## Calendar semantics

Query ranges are half-open: `[start_at, end_at)`. An Appointment overlaps when its
arrival start is before the query end and its arrival end is after the query start.
An Appointment ending exactly at the query start or starting exactly at the query end
does not overlap. Draft Appointments without both arrival boundaries are excluded.
Ranges must be timezone-aware, strictly increasing, and no longer than 93 days.

Results order by:

1. arrival-window start;
2. arrival-window end;
3. Appointment number;
4. Appointment identifier.

## Security and permissions

Reads require `COMPANY_SCHEDULING_READ`. Mutation authority remains independently
controlled by `COMPANY_SCHEDULING_MANAGE`; ACP Enterprise has no implicit permission
inheritance. Company and all authorized Branch identifiers originate from the frozen
AuthorizationContext. Detail and search SQL include those predicates, so inaccessible
and cross-Company records are concealed rather than filtered after loading.

Fresh bootstrap installations persist and grant both canonical Scheduling permissions
under the existing initial-administrator policy. Existing installations intentionally
run `python -m app.platform.permissions.sync_catalog`, then assign the read permission
through Company Administration and reauthenticate. Synchronization does not grant it.

## Response and capacity model

Appointment detail and summary schemas use typed UUIDs, lifecycle enums,
timezone-aware datetimes, and Decimal capacity. Arrival, duration, and capacity remain
nullable because valid draft persistence may omit them. Capacity is read from the
single Appointment reservation without exposing ORM records.

## Extension rules

Future Technician, Dispatcher, Route, priority, Job, Estimate, Invoice, and AI filters
extend `AppointmentQuery` and its single repository compiler. They must not introduce
consumer-specific tenant filtering or duplicate calendar SQL. Technician ownership,
assignment, route optimization, and custom reporting projections remain outside this
workstream.
