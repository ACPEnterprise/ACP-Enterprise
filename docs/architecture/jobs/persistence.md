# Jobs Persistence Foundation

## Ownership and tables

Jobs owns three tables:

- `job_number_sequences` allocates atomic Company-scoped `JOB-000001` numbers.
- `jobs` stores the aggregate's current durable state and attribution.
- `job_appointment_links` stores Jobs-owned associations to Scheduling visits.

Company, Branch, Customer, Service Location, Appointment, and User records remain
owned externally. All foreign keys use `RESTRICT`. Jobs persistence never mutates an
external table.

## Numbering and transactions

`JobRepository.next_job_number` performs PostgreSQL `INSERT ... ON CONFLICT DO
UPDATE ... RETURNING` against the Company-keyed sequence row. The row update
serializes concurrent allocators. Allocation and Job insertion occur in the future
service transaction, so rollback restores the counter; a committed Job number is not
reused. Numbers are allocated when a draft is created.

## Integrity and lifecycle

The database constrains the six approved lifecycle values, canonical priority,
positive concurrency versions, Job-number format, normalized Job-type-code shape,
and coherent activation, start, pause, completion, cancellation, and timestamp
metadata. `status` is the sole authority for the current lifecycle state.

Completion and cancellation attribution groups retain the most recent corresponding
terminal occurrence. Each group is either wholly populated or wholly null, and the
matching terminal status requires its group. A later `ready` state may retain either
or both complete groups after reopening; their presence does not imply that the Job
is currently terminal. A reopened, previously started Job may likewise retain
`started_at` while `ready`.

Pause fields describe only an active pause and are cleared on resume. Reopen is a
future operation returning a terminal Job to `ready`; reopen snapshot fields and
lifecycle/pause history tables are intentionally absent. Full lifecycle history is
deferred to durable Business Events or a future reviewed projection.

Priority ordering is `low < normal < high < urgent < emergency`. Job type remains an
extensible lowercase code rather than a fixed product enum.

## Cross-domain validation

Composite foreign keys enforce Company/Branch agreement with Platform Branches and
with both sides of each Appointment link. Validation-only PostgreSQL triggers enforce
Customer-to-Company, Service-Location-to-Customer, and linked Appointment Customer
and Service Location agreement. Companion parent-side triggers prevent later
Customer, Service Location, Job, or Appointment identity changes from invalidating a
persisted reference.

The triggers reject invalid writes and never alter Customer or Scheduling data.
Future service validation must use a narrow immutable Scheduling reference contract;
the Jobs repository must not become a general SQL owner for Scheduling.

## Appointment association

The database permits one Appointment to link to multiple Jobs. It rejects duplicate
`(job_id, appointment_id)` pairs and duplicate visit sequence within a Job, while the
same visit sequence remains valid across Jobs. The future service normally permits
one Job per Appointment and must enforce that policy transactionally. No database
uniqueness constraint on `appointment_id` encodes that future policy.

## Repository boundary

`JobRepository` owns atomic number allocation, Job insertion, Company-scoped lookup,
Company-scoped row locking, link insertion, and Company-scoped ordered link loading.
It returns ORM aggregates only on the internal mutation boundary, matching existing
Customer and Scheduling repositories. Future read consumers require immutable DTOs
through a dedicated Job Query Engine.

The repository does not authorize, decide lifecycle transitions, begin or complete
transactions, stage events, expose HTTP behavior, or mutate another domain.

## Deferred work

Services, commands, events, permissions, query DTOs, APIs, frontend, Dispatch,
assignments, labor, inventory, estimates, invoices, payments, attachments, forms,
warranties, route optimization, GPS, and ACP-EIQ behavior are future milestones.
