# Persistent Worker Operations

## Authoritative path

Engineering Control approves work. Engineering Execution creates the immutable
offer. Worker Control owns its lease. Authenticated Worker Transport proves the
worker identity and message order. The worker performs only the typed bounded
operation, signs the structured result, and the backend durably records it for
status projection and owner review.

```text
Engineering Control → Engineering Execution → authenticated offer → worker lease
→ authenticated transport → bounded execution → signed result → durable result
→ owner review
```

## Service boundary

Preview uses the existing Docker Compose worker service with
`restart: unless-stopped`; no interactive shell or second orchestration system is
required. The container is read-only, drops all Linux capabilities, prevents
privilege escalation, mounts the private key read-only, mounts the bounded
workspace read-only, and writes only non-secret health and recovery state to its
dedicated volume.

The key path must be absolute and owner-only. Authentication, credential status,
Company binding, capability intersection, offer eligibility, and lease ownership
are revalidated by durable backend state. Revoked, expired, replaced, malformed,
or cross-Company identities fail closed.

## Recovery truth

The worker persists one owner-only recovery record before beginning execution:

- `acquired`: a crash may have interrupted execution; restart changes this to
  `reconciliation_required` and never automatically executes the offer again.
- `pending_result`: bounded execution completed; restart establishes a new
  authenticated session and redelivers the same domain result. Server-side
  idempotency prevents a duplicate repository operation or result.
- `reconciliation_required`: heartbeats remain degraded and no new offer is
  acquired until an operator reconciles durable backend and workspace truth.

Temporary transport, backend, or network failure moves the process to degraded,
clears only the ephemeral session, and reconnects with bounded exponential delay.
It does not erase recovery truth or re-execute work. A stale heartbeat therefore
cannot remain healthy, while Compose restarts the process after host or process
restart.

## Observability

The backend remains authoritative for worker ID, connection/session state,
heartbeat age and health, lease state, command/execution reference, and durable
result. The local Compose health check accepts only a recent successful
authenticated heartbeat. Its bounded evidence contains only worker ID, heartbeat
time, and deployed service version—never credentials, tokens, headers, environment
values, logs, keys, repository contents, or result payloads.

The existing authenticated Engineering Control status projection remains the
PHONE.4-facing contract. PHONE.5 does not change its API or frontend ownership.
