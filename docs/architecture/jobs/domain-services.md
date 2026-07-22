# Jobs Domain Services

## Aggregate boundary

`JobService` is the sole public mutation owner for Job creation, metadata,
Appointment links, lifecycle, concurrency versions, and Jobs-owned Business Events.
Each public mutation opens one application-session transaction. Repositories own SQL
and mapped persistence changes but never authorization, transitions, events, commit,
or rollback.

Commands are frozen transport-independent values. Company, actor, Membership,
permissions, and authorized Branches come from immutable `AuthorizationContext`, not
client-supplied command fields.

## Reference boundaries and locking

Customer Management exposes an immutable Customer/Service Location reference.
Scheduling exposes an immutable `AppointmentReference`; its locked lookup is the
serialization point for the normal one-Job-per-Appointment policy. Neither contract
leaks mapped objects or grants Jobs authority to mutate another domain.

Appointment operations lock in this order:

1. Appointment.
2. Customer and Service Location validation records.
3. Existing Job, when applicable.
4. Jobs-owned Appointment links.
5. Company Job-number sequence, when creating.

After the Appointment lock, existing Jobs-owned links are inspected. An identical
Job/Appointment/visit link is a no-op; another relationship is rejected. This avoids
an unlocked empty-set race while retaining the structurally many-to-many schema for a
future explicitly approved workflow.

## Lifecycle and retries

The implemented transitions are `draft → ready`, `draft|ready → cancelled`,
`ready → in_progress`, `in_progress → paused|completed`, `paused → in_progress`, and
`completed|cancelled → ready`. Active-work cancellation is deliberately unsupported.

All non-create mutations lock the Job and check `expected_version`. Narrow no-op
retries exist only for an identical pause reason, cancellation reason, completion by
the same actor, or Appointment link. Other repeated operations are ordinary lifecycle
or version conflicts. Create has no general idempotency key.

Reopening preserves completion, cancellation, and start history, clears only current
pause fields, and establishes activation when reopening a draft-cancelled Job.

## Guards and events

Completion, cancellation, and reopening guards are extension protocols. Empty guard
collections are valid; unfinished modules contribute no placeholder queries. Guards
receive immutable Job facts and run before mutation and event staging.

Every operation captures one UTC occurrence time and one correlation ID. All events
from that operation share them and are staged in the domain transaction. Payloads use
stable identifiers, controlled codes, status changes, and versions; they exclude
contact details, addresses, descriptions, credentials, and mutable snapshots. No
event is staged for a no-op retry.
