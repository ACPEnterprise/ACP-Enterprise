# Durable Notification Outbox

## Purpose and boundary

The notification outbox is ACP Enterprise's durable handoff between a business
transaction and future asynchronous delivery. A business service writes a
delivery intent through `NotificationOutboxRepository` in the same PostgreSQL
transaction as the state change. Delivery never occurs inside that transaction.

```text
Business service
→ NotificationOutboxRepository
→ PostgreSQL commit
→ future notification worker
→ future notification provider
```

The repository owns SQL, deterministic ordering, pagination, row locking, claim
tokens, and persistence transitions. It does not commit, choose retry policy,
generate tokens, publish events, or contact providers. The future worker will own
retry policy and provider coordination. Provider contracts are deliberately
transport-neutral so SMTP, SendGrid, Amazon SES, Mailgun, SMS, voice, and push can
be added without changing business services or outbox persistence.

## Persistence contract

Each record contains a notification and template identifier, recipient,
structured JSON payload, correlation identifier, globally unique idempotency
key, lifecycle status, retry count, terminal-failure marker, scheduling and claim
metadata, controlled error codes/categories, and audit timestamps. Payloads may
contain only the minimum delivery metadata needed by a reviewed template. They
must never contain passwords, plaintext verification/recovery/session tokens,
credential hashes, provider secrets, or arbitrary exception text.

The initial lifecycle is:

```text
pending → claimed → sent
                 ↘ retry_scheduled → claimed
                 ↘ failed (terminal/dead-letter eligible)
```

Database checks keep lifecycle timestamps and claim state consistent. A unique
idempotency key prevents duplicate intent creation. Terminal `failed` records are
dead-letter eligible; the future worker will own maximum-attempt and backoff
policy rather than embedding operational policy in the repository.

## Claiming and horizontal scaling

Workers will call `claim_batch` inside a transaction. PostgreSQL selects ready
`pending` or `retry_scheduled` rows in `(scheduled_at, created_at, id)` order with
`FOR UPDATE SKIP LOCKED`. Each selected record receives the worker identifier and
a unique claim token before commit. Parallel workers therefore receive disjoint
batches without a global process lock.

Completion, terminal failure, and retry scheduling require both record ID and the
active claim token. A stale worker cannot complete a notification after its claim
has been released and reassigned. Abandoned claims are released by an explicit
maintenance operation using a caller-selected timeout. Completed records may be
deleted in bounded, ordered batches after an externally configured retention
period; no automatic cleanup or worker exists in this milestone.

## Transaction lifecycle and failure behavior

An identity email-change request and its notification intent commit atomically.
If identity validation, outbox insertion, Business Event staging, Audit staging,
or commit fails, neither the identity request nor notification becomes visible.
The unique idempotency key makes a repeated enqueue return the existing record
without generating another delivery intent.

The current identity integration queues only the pending-change and User resource
identifiers plus the destination address. It intentionally does not persist the
plaintext verification token. A production delivery milestone must add a
reviewed, secret-safe handoff (for example, a short-lived encrypted delivery
artifact or purpose-built issuance-at-delivery protocol) before enabling email.
No provider can send an email from this foundation alone.

## Future worker and provider responsibilities

The future worker will:

1. release claims older than its configured lease;
2. claim a bounded batch in one short transaction;
3. build a provider message without logging sensitive data;
4. deliver outside the database transaction;
5. mark the claim sent, schedule a controlled retry, or mark it terminally failed;
6. emit operational metrics and controlled security/audit signals as approved.

Network calls must never keep a PostgreSQL transaction or row lock open. Provider
implementations receive a typed message and return a controlled result; they do
not mutate outbox rows. Provider credentials remain external secrets and never
enter outbox payloads.

## Non-goals

This foundation does not implement a worker, email rendering, provider selection,
SMTP or vendor integration, retry/backoff policy, delivery webhooks, production
email delivery, or notification APIs.
