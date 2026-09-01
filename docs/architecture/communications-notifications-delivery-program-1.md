# Transactional communications and notification delivery

## Authority and capability audit

`COMMUNICATIONS.NOTIFICATIONS.DELIVERY.PROGRAM.1` composes the authoritative notification outbox, Identity Onboarding invitation authority, Communications request/history domain, and protected-artifact contracts. It does not create a second queue, choose a provider, enable a worker, or send a communication.

| Capability | Classification | Result |
| --- | --- | --- |
| Durable tenant-scoped outbox, claims, recovery, ambiguity | AUTHORITATIVE | Reused unchanged as the only queue |
| Immutable delivery-attempt evidence | AUTHORITATIVE | Extended with provider acceptance and idempotent provider-event identity |
| Employee invitation secret/envelope, expiry, revoke, reissue, activation | AUTHORITATIVE | Composed with delivery state; secret remains outside outbox/logs |
| Customer communication preparation/history | AUTHORITATIVE | Existing consent, recipient, source Event, Company and Branch checks retained |
| Estimate protected-delivery preparation | PARTIAL | Deterministic protected-document renderer binds exact artifact digest; real delivery remains gated |
| Service Agreement notice | POLICY_REQUIRED | Contract can render a protected notice, but cadence and recipient authority remain unconfigured |
| Provider adapter and dispatch | PROVIDER_REQUIRED | Typed provider interface and synthetic adapter complete; live adapter/runtime disabled |
| Provider webhooks | PROVIDER_REQUIRED | Authenticity/idempotency/tenant contract complete; no live endpoint/provider secret configured |
| In-product read/unread Notification Center | ABSENT | Separate authority decision required; not inferred from transactional delivery |
| Universal Document Center | POLICY_REQUIRED | Cross-domain authorization/retention requires a separate accepted product boundary |

## Transactional message contract

The ACP identity remains the notification outbox UUID, not a provider identifier. Durable intent binds Company, optional Branch, message type, recipient/reference, channel, template/version, minimum rendering inputs, intent digest, source action/Event, actor, correlation, idempotency key, lifecycle, and timestamps. The provider receives a rendered message plus a stable idempotency key where supported. Provider IDs are safe secondary references.

Current message types are bounded to existing authority: onboarding invitation, accepted Customer appointment/technician/Estimate notices, protected Estimate/document preparation, and future Service Agreement notices once policy is configured. Marketing campaigns and generalized broadcast sending are excluded.

## Template and secret boundary

The invitation renderer is deterministic and versioned as `identity-onboarding-invitation-v1`. It produces subject, escaped HTML, plain text, and a SHA-256 content digest. Display values reject header newlines. Protected links require HTTPS, an exact configured origin, no embedded credentials, and no fragment. The message contains an Activate Account action and no password.

The activation secret remains encrypted in `ProtectedInvitationDeliveryEnvelope` until a provider resolver claims it in memory. It is never persisted in the outbox, evidence, audit, Business Events, provider metadata, or ordinary logging. Successful protected delivery destroys the encrypted envelope through the existing onboarding service. Delivery status never grants activation authority; invitation expiry, revocation, single use, and credential establishment remain decisive.

## Truthful delivery lifecycle

The durable lifecycle distinguishes:

`pending -> claimed -> submitted -> accepted -> delivered`

and controlled alternatives:

`retry_scheduled`, `failed`, `ambiguous/uncertain`, `canceled`, and `suppressed`.

Provider acceptance is not delivery. An accepted item has submission evidence and a provider reference but no delivered timestamp. An authenticated provider event may move it to delivered, deferred, bounced/rejected/complaint. Duplicate provider events use `(outbox_id, provider_event_key)` idempotency. Later contradictory events cannot rewrite a terminal delivered/failed/canceled/suppressed outcome.

An uncertain result is never retried blindly. Automatic retry after submission is permitted only where the configured provider supports the stable idempotency key. Retry bounds/backoff remain explicit runtime policy; this program does not invent Production constants.

## Worker and provider gate

`TransactionalDeliveryService` executes exactly one already-durably-claimed item. It does not acquire work, schedule itself, commit, or own the general worker runtime. The current Enterprise scheduler remains untouched. Live dispatch is disabled until a provider adapter, credential secret, sender/domain evidence, retry policy, and deployment worker registration are separately approved.

`SyntheticNotificationProvider` is deterministic, performs no network access, and qualifies accepted, delivered, deferred, bounced, rejected, and uncertain outcomes.

## Webhooks, bounce, and suppression

The provider-neutral webhook contract requires an authenticity verifier before persistence. It binds a provider reference to the owning Company, records a stable provider event key, tolerates duplicate delivery, and fails closed for unknown tenants/messages/outcomes. Hard bounce, rejection, complaint, and suppression are evidence states; no unapproved Employee or Customer business consequence is inferred.

## Administration product

Identity Onboarding now exposes a Company/Branch-authorized delivery projection. The responsive Administration workspace shows invitation state, delivery state, template version, attempt count, safe error code, and whether provider evidence exists. It supports refresh, canonical reissue, and revoke only while onboarding remains invited. Pending items truthfully state that the provider is not configured. Raw provider responses, message bodies, tokens, and SQL errors are absent.

Customer Communication History remains scoped and read-only. A universal communications mutation center and a universal Document Center are not created.

## Authorization, tenancy, privacy, and retention

- Identity delivery history and resend/revoke reuse `COMPANY_IDENTITY_ONBOARDING_MANAGE` and existing Branch checks.
- Customer preparation/history retain `COMPANY_COMMUNICATIONS_MANAGE` and `COMPANY_COMMUNICATIONS_READ`.
- Provider events require both verified authenticity and a Company-bound provider reference.
- Transactional account activation is distinct from Customer marketing consent. Existing Customer consent/preference gates remain in force.
- Durable evidence stores identities, digests, states, safe classifications, and timestamps—not body content, credentials, activation tokens, or protected payloads.
- No body-retention period is invented; rendered bodies are transient at dispatch. Immutable intent/audit/evidence retention remains governed by existing Platform policy.

## Provider and domain readiness decision packet

ACP requires a transactional provider with API authentication held outside ACP data, verified-domain sending, DKIM/SPF support and DMARC compatibility, sandbox/test behavior, stable message references, delivery/bounce/complaint events, authenticated webhooks, suppression handling, and an understood idempotency/reconciliation contract.

Candidate families for owner evaluation are Amazon SES, Postmark, Twilio SendGrid, and Mailgun. The implementation deliberately does not rank or select them. Before activation, the owner must approve: provider, account/region, sending domain, From/Reply-To identities, domain-verification/DNS work, credential custody, webhook ingress, retry/attempt policy, suppression policy, and non-Production recipient allow-list. ACP must retain `PROVIDER_NOT_CONFIGURED` until that evidence exists.

## Lianne readiness

No real Employee or address was inspected or created. The first-real-employee packet is therefore:

- Employee existence: NOT INSPECTED / OWNER DATA REQUIRED
- Invitation readiness: READY once an authorized Employee onboarding record and verified recipient exist
- Template: `identity-onboarding-invitation-v1`
- Provider: NOT CONFIGURED
- sender/domain: NOT VERIFIED
- activation URL: contract ready; environment origin configuration required
- send permission: `COMPANY_IDENTITY_ONBOARDING_MANAGE` plus enabled provider runtime
- expected evidence: prepared, queued, submitted, accepted, delivered/bounce/failure, then independently activated

Do not guess Lianne Hernandez's email and do not send until the owner separately authorizes a real non-Production delivery after provider/domain readiness.

## Remaining authority decisions

Provider selection and credentials, sender/domain/DNS verification, retry bounds, complaint/suppression operations, Service Agreement cadence, user read/unread Notification Center lifecycle, cross-domain Document Center authorization, and retention periods remain explicit gates. Preview and Production are untouched.
