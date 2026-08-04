# Realtime Mission Control

PHONE.6 connects the persisted PHONE.4 owner-control model to the authenticated
PHONE.5 worker runtime without changing either authority boundary.

## Authoritative pipeline

1. Owner intent or authenticated worker runtime changes are committed to
   `engineering_workstream_events` in the same database transaction as their
   authoritative projection.
2. A PostgreSQL `AFTER INSERT` trigger publishes only the Company and event ID
   through `NOTIFY`. The notification is a wake-up hint; it is not durable
   truth.
3. `GET /api/v1/engineering/mobile/events` applies the existing bearer,
   Company-scope, active-membership, and Engineering Control read permission.
4. The SSE service reads ordered events from PostgreSQL and emits bounded,
   non-sensitive projections. The request database connection is released
   before the long-lived stream begins.
5. Mission Control merges the event directly into its list and detail caches.
   It does not poll or request a current-state refresh after an event.

## Resume and delivery

Each SSE frame uses the durable event UUID as `id`. A client reconnects with
`Last-Event-ID` or `after`; the server validates that token inside the current
Company and resolves it to a database-assigned monotonic sequence. Events are
returned by that sequence, independent of clock skew. The browser stores
the last applied ID per Company in session storage and suppresses a repeated
frame. Unknown tokens fail closed with `409`; the client clears only that
Company's unusable cursor and reconnects from durable retained truth.

PostgreSQL notifications may be coalesced or dropped without losing events.
Every wake-up causes another persisted-event query after the last cursor; the
server-side heartbeat watchdog also checks expiry on keepalive. Replays are
capped at 500 rows per query and continue until caught up.

## Runtime truth and notifications

The stream projects owner requests, worker acknowledgements, runtime progress,
validation, Preview deployment, completion, failure, recovery, heartbeat
expiry, and worker disconnection classifications. A five-minute stale heartbeat
is transactionally converted once into an unhealthy `recovering` projection and
a durable `heartbeat_expired` event.

Notification classifications are bounded to waiting for owner, completed,
failed, recovering, heartbeat expired, worker disconnected, deployment
completed, and deployment failed. They contain no credentials, tokens, request
headers, logs, repository contents, or environment data.

## Metrics

Event projections expose acknowledgement, execution, validation, and deployment
latency, plus worker uptime and distinct-session reconnect count. Metrics are
derived from persisted Company-scoped event history, so reconnect and replay do
not change their values.

## Preview readiness

Deployment requires the PHONE.4 and PHONE.5 migrations followed by
`g2c4e6a8b153`. Preview's reverse proxy must disable buffering for the SSE path
and retain normal authentication headers. PostgreSQL remains the only required
event durability and fan-out mechanism; no second queue or orchestration system
is introduced.
