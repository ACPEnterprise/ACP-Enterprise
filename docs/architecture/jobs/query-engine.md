# Jobs Query Engine

## Authoritative read flow

All Jobs consumers use `JobsQueryService`, immutable query intent, and
`JobQueryRepository`. The service derives an internal frozen `JobQueryScope` solely
from immutable `AuthorizationContext`; callers cannot provide Company or authorized
Branch scope. Repository SQL applies both predicates before retrieval. Missing,
cross-Company, and inaccessible-Branch detail requests are indistinguishable.

Detail and search intent are separate frozen dataclasses. They contain filters,
sorting, and pagination only—never SQL, ORM objects, sessions, HTTP types, or security
scope. The repository returns frozen ORM-free DTOs and never locks, mutates, flushes,
commits, rolls back, or publishes events.

## Projections and cross-domain reads

Detail includes current and historical Job lifecycle facts, live Customer and Service
Location display projections, and ordered Appointment summaries. `status` remains the
current lifecycle authority; completion and cancellation fields may describe history
on a reopened `ready` Job.

Customer display values are live joins, not Jobs-owned snapshots. The location label
is `nickname-or-address, city, state, postal-code`. Contact details and sensitive
property fields are excluded. Scheduling remains authoritative for Appointment facts.
Detail uses one scoped Job/display query plus one ordered Appointment query, avoiding
N+1 access.

List queries remain one row per Job. Correlated `EXISTS` implements Appointment
filters and Appointment-number search. Scalar subqueries provide Appointment count
and `earliest_appointment_start_at`, defined as the minimum non-null linked arrival
start regardless of past or future time.

## Search, filters, and ordering

Exact normalized `job_number` is distinct from partial `search_text`. Operational
search covers Job number, Customer display/legal name, Service Location street/city/
postal code, customer-reported problem, and linked Appointment number. Input is
trimmed, case-insensitive, nonblank, and limited to 200 characters. Internal notes,
contacts, access instructions, and financial data are excluded.

Date filters are timezone-aware half-open ranges `[start_at, end_at)` without a
domain-wide maximum duration. Historical completion/cancellation filters are
independent of current status.

Controlled ordering supports Job number, canonical priority rank, lifecycle rank,
timestamps, Customer display name, and earliest Appointment start. Lifecycle rank is
`draft`, `ready`, `in_progress`, `paused`, `completed`, `cancelled`. Nullable values
use `NULLS LAST`; Job ID ascending is always the final tie-breaker.

Offset pagination defaults to page 1 and 50 items, with a maximum of 200. Count and
page queries share identical Job-level filters. Empty out-of-range pages retain total
count and total-page metadata.

## Performance and extension policy

Existing Company, Branch, status, priority, Customer, Service Location, completion,
number, link, and Customer/address trigram indexes support the initial engine. New
indexes require measured PostgreSQL plan evidence and a separately reviewed
persistence amendment. Future typed filters may extend the same engine when their
domains exist; no consumer creates a parallel Job SQL path.
