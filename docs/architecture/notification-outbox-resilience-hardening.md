# Notification Outbox Resilience Hardening

## Authority and scope

`BANK.PLAT.006` hardens the existing `notification_outbox` contract. It does not
introduce a second notification system, a new channel, or a live provider. The
repository remains the durable boundary between an accepted notification intent
and a provider adapter. Domain services remain responsible for creating the
intent in the same transaction when their contract requires atomic creation.

## Delivery guarantee

ACP provides a durable outbox and at-least-once physical delivery attempts.
Logical provider submission is effectively once only when the selected provider
honors the stable provider idempotency key. ACP does not claim exactly-once
external delivery.

An accepted intent has one stable idempotency key and a canonical SHA-256 intent
digest. Exact replay resolves to the same item. Reuse of the key with different
facts fails closed. Historical rows created before the digest existed remain
replayable only when their original stored facts match exactly.

## Lifecycle and evidence

The lifecycle is:

`pending -> claimed -> sent | retry_scheduled | failed | ambiguous`

An unsubmitted expired claim returns to `pending` or `retry_scheduled`. An
expired claim after provider submission becomes `ambiguous` unless provider
idempotency makes another attempt safe. Explicitly authorized pre-delivery
disposition may produce `canceled` or `suppressed`.

Every acquisition and outcome appends immutable delivery evidence. Evidence
records the outbox, tenant scope, worker/claim, safe provider reference, failure
classification, actor or reason digest, and timestamp. Database triggers reject
evidence update and deletion. Terminal cleanup archives the item; it does not
delete the intent or its evidence.

## Provider ambiguity, retry, and recovery

Provider submission is recorded before an outcome is asserted. If a response is
lost, ACP records an ambiguous outcome and does not call it delivered or failed.
Without provider idempotency, an ambiguous item cannot be automatically retried.
No retry interval or maximum-attempt business policy is invented here; the
repository supports explicit bounded scheduling by its caller.

Durable row locks and `SKIP LOCKED` prevent two workers from owning the same
claim concurrently. Claims carry an expiry. Recovery preserves original intent,
attempt lineage, tenant scope, and provider evidence. A crash after provider
submission therefore converges to either a recorded outcome or explicit
ambiguity, never false success.

## Events, recipients, content, and isolation

Callers may bind the original Business Event and source action to the intent.
Event replay must reuse the notification idempotency identity, so it cannot
manufacture a second intent or resend a terminally delivered item. The outbox
stores authoritative recipient/channel references and content/template version;
it does not infer contact data, consent, or channel preference.

Consent and suppression remain domain-policy decisions. The outbox preserves an
authorized suppression/cancellation outcome and will not deliver it. Manual
disposition requires explicit authorization and a SHA-256 reason digest.

Company and Branch identities are copied into immutable attempt evidence.
Provider workers and operator services must use the accepted tenant-scoped
authorization boundary; delivery evidence never changes tenant scope. Provider
references and error codes must be safe metadata. Credentials, raw provider
secrets, payment material, and unnecessary message payloads are prohibited from
delivery evidence.

## Qualification and extension

Qualification uses repository-owned synthetic recipients and provider
references only. A provider adapter must declare whether it supports stable
idempotency before automatic recovery can rely on that guarantee. New channels
must reuse the same intent digest, claim, evidence, ambiguity, tenant, and audit
contracts and add provider-specific tests without weakening them.

The current identity-email and Communications producers already create durable
outbox intent transactionally. Communications additionally validates recipient,
contact, consent, source-event, Company, and Branch authority before enqueue.
No live email, SMS, push, Slack, or other provider was contacted by this
milestone.
