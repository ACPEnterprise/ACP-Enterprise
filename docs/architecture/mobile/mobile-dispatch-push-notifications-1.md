# MOBILE.DISPATCH.PUSH.NOTIFICATIONS.1

Status: `BLOCKED_ON_OM2C_CANONICAL_ASSIGNMENT_EVENT`

## Start gate

Mobile implementation must not begin until OM2-C proves the real FIELD_TECH
chain in Beta:

`real Employee -> eligible Workforce profile -> sanctioned Appointment/Job -> Dispatch assignment -> Employee My Day -> assigned Job`

The proof must use the real Beta acceptance identity **Michael Brian** or an
explicitly sanctioned equivalent field employee. Synthetic assignment data,
client-provided Employee identity, and a schedule without an accepted active
assignment do not satisfy the gate.

OM2-C must publish one canonical assignment/schedule Business Event contract
before Phone/Mobile consumes it. Existing assignment and appointment events are
useful source history, but are not by themselves the complete Mobile push
contract because they do not yet normalize all notification causes and
recipient/deep-link evidence.

## Required canonical event contract

The event must be durable, Company/Branch scoped, append-only, versioned, and
contain:

- `event_id`, `event_type`, `schema_version`, `occurred_at`, `correlation_id`
- Company, Branch, Appointment, Job, and Dispatch Assignment identities
- prior and current assignment/appointment versions
- authorized Employee recipient identity and assignment scope
- schedule window and timezone where applicable
- priority/emergency state where applicable
- material-access/customer-instruction revision digest where applicable
- source action and actor identity
- canonical Mobile deep-link target (`My Day` or assigned Job)
- idempotency/coalescing identity
- evidence digest and limitations

Required normalized causes:

1. `ASSIGNMENT_CREATED`
2. `ASSIGNMENT_REASSIGNED`
3. `SCHEDULE_CHANGED`
4. `ASSIGNMENT_CANCELLED`
5. `PRIORITY_CHANGED`
6. `MATERIAL_ACCESS_OR_CUSTOMER_INSTRUCTION_CHANGED`

One Dispatch edit that changes multiple backend fields must produce one
logical notification intent, not one push per changed column. Coalescing must
use the canonical assignment/appointment revision and cause set, with durable
history of the source event IDs.

## Mobile delivery path after gate

`Business Event -> notification intent/outbox -> event-driven delivery worker -> APNs -> employee device -> My Day/assigned Job deep link`

The existing durable notification outbox and delivery evidence remain the
queue/history authority. Mobile must not poll for assignment changes when the
event-driven path is available. Push delivery is at-least-once transport with
idempotent logical application; it must expose accepted, delivered, deferred,
failed, ambiguous, and unavailable states without claiming device display when
APNs evidence is absent.

APNs/provider credentials, device-token enrollment, notification permission,
and Production delivery remain provider/human gates. No provider is selected or
configured by this milestone.

## Authorization and privacy

- Recipient selection is server-authoritative from the current active Employee and assignment scope.
- Company/Branch/assignment authorization is revalidated before creating the intent and before deep-link resolution.
- Lock-screen content is minimal and must not expose sensitive Customer, payment, payroll, or internal notes.
- A deep link is only a locator; My Day/Job APIs repeat current authorization and assignment checks.
- Revoked, released, foreign, or stale assignments must fail closed.

## Acceptance criteria

1. OM2-C proves Michael Brian’s real Beta assignment chain end to end.
2. Each of the six normalized causes produces one bounded notification intent.
3. Multi-field Dispatch edits coalesce into one logical notification.
4. Replayed Business Events do not duplicate delivery intents.
5. Reassignment stops the previous Employee’s future notification eligibility.
6. Device deep links open only authorized My Day or assigned Job context.
7. Notification history and delivery evidence are queryable by authorized operators.
8. APNs unavailable/configuration-missing states remain explicit and fail closed.
9. No polling loop is introduced where durable events are available.

## Current disposition

`NOT_READY_FOR_IMPLEMENTATION`: OM2-C real FIELD_TECH acceptance and the
canonical normalized assignment/schedule event contract are still required.
