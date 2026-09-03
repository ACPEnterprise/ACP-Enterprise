# Communications Operational Measurement 1

## Authority

Communications delivery truth remains the durable notification outbox and its immutable delivery evidence. The `communications-operational-v1` projection is read-only: it aggregates accepted evidence and cannot submit, retry, suppress, or otherwise mutate a communication.

The projection is Company-scoped and optionally Branch-scoped through the requesting principal's existing Communications read permission. Its deterministic fingerprint binds the scope, measurement version, observed lifecycle counts, and final outbox truth. It contains no recipient, message body, provider payload, or provider credential.

## Measured evidence

Observed evidence distinguishes submitted, accepted, delivered, failed, bounced/rejected recipient, suppressed, ambiguous/uncertain submission, technical retry, abandoned-claim recovery, and authenticated webhook replay. Final truth separately classifies pending, provider-accepted but not delivery-confirmed, delivered, failed, suppressed, and uncertain messages.

Authenticated duplicate delivery callbacks append a `webhook_replay` observation containing a digest of the provider event identity. They do not repeat the provider outcome, alter final delivery truth, or disclose the raw webhook payload. Existing database enforcement keeps all delivery evidence append-only.

## Boundaries

- Consent, DNC, SMS STOP/START, unsubscribe, and suppression authority are unchanged.
- Measurement does not make provider acceptance equivalent to delivery.
- An uncertain submission is not retried by measurement and remains reconciliation-required.
- Economics, Luminary, or operations may later consume these provider-neutral counts as operational evidence; they may not treat them as revenue, Customer intent, or mutation authority.
- Qualification uses only the deterministic synthetic provider and authenticated synthetic webhook verifier. No real provider is configured and no real communication is sent.
