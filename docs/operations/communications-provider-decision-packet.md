# Communications provider selection and activation packet

## Current decision

Status: **OWNER_PROVIDER_SELECTION_REQUIRED**.

ACP has no authoritative Email or SMS provider selection. This packet does not
rank, recommend, contract with, configure, or activate a vendor. It defines the
minimum evidence an owner-approved provider must satisfy before Preview testing.

## Provider capability requirements

| Capability | Email | SMS | Admission evidence |
| --- | --- | --- | --- |
| Authenticated server API | Required | Required | Server-side credential reference and rotation procedure |
| Non-production testing | Required | Required | Sandbox/test mode or sanctioned-recipient isolation |
| Stable provider message identity | Required | Required | Acceptance response contract |
| Idempotent submission or status reconciliation | Required | Required | Documented same-key retry or message-status lookup |
| Delivery webhook | Required | Required | Signed events with unique event identity |
| Failure detail | Bounce, reject, defer | Reject, defer, undelivered | Safe normalized outcome mapping |
| Recipient controls | Unsubscribe/suppression evidence where applicable | STOP/START/HELP evidence | Authenticated control event and destination digest |
| Throttling | Required | Required | Published rate-limit signal and retry guidance |
| Sender admission | From identity and domain verification | Number/sender verification and required registration | Provider-owned verification evidence |
| Content | UTF-8 text/HTML; protected links; attachments only if later authorized | UTF-8 SMS with segment visibility | Rendered-content digest preserved before transport |
| Operations | Service health and incident visibility | Service health and incident visibility | Monitoring and escalation path |
| Audit | Exportable acceptance/delivery evidence | Exportable acceptance/delivery evidence | Retention and access controls |

Provider templates are optional. ACP remains the authority for business facts,
template version, personalization, and content digest. A provider must not become
the source of Customer, Job, Scheduling, Estimate, Invoice, or identity truth.

## Sender identity requirements

Email activation requires an owner-approved display name, From address/domain,
Reply-To behavior, provider verification, and applicable DNS evidence. SMS
activation requires an owner-approved number or sender identity, geographic and
use-case eligibility, required registration, and approved STOP/START/HELP text.
None is assumed verified today.

## Secure configuration contract

Preview and Production use independent provider accounts or isolated
subaccounts, credentials, sender identities, webhook secrets, and test-recipient
controls. Raw credentials never enter Git, frontend configuration, logs, API
responses, screenshots, or evidence packets.

Server configuration requires:

- `COMMUNICATIONS_DELIVERY_ENABLED`
- Email/SMS provider identities
- Email/SMS credential **references**, not credential values
- verified Email sender and domain evidence
- verified SMS sender and registration evidence
- webhook secret **reference** and explicit webhook enablement

Delivery remains disabled unless all required server-side references exist.
Production values must never be installed in Preview.

## Consent and suppression admission

Possession of an address or number is not consent. Preview acceptance must prove
authoritative recipient derivation, current channel consent where required, and
request-time suppression. Marketing/outreach opt-out is distinct from
transactional, operational, account-security, and internal purpose. Any legal or
Company exception to STOP, DNC, unsubscribe, bounce, provider suppression, or
administrator suppression remains **POLICY_REQUIRED**; fail-closed behavior is
the default until that policy exists.

## Webhook requirements

The selected provider adapter must verify signature/authentication before event
parsing, enforce an accepted timestamp/replay window, bind a configured provider
identity and secret version, normalize a unique provider event identity, recover
Company scope from the correlated message rather than caller input, reject or
quarantine unknown message identities, and log no raw recipient, body, token, or
secret. Duplicate and out-of-order events must append evidence without rewriting
unrelated business authority.

## Shortest safe Preview acceptance sequence

1. Owner selects provider(s), account isolation, sender identities, and policy.
2. Provision Preview-only accounts, secret references, verified senders, and
   signed webhook endpoints while delivery remains disabled.
3. Configure an allow-list containing only sanctioned synthetic recipient(s).
4. Validate readiness, configuration isolation, disable switch, and secret scan.
5. Enable Preview and send one transactional synthetic Email and SMS.
6. Verify submission identity, accepted-not-delivered distinction, delivery
   webhook, duplicate webhook, deferred-then-delivered, rejection, bounce, and
   authenticated STOP/START handling.
7. Simulate response loss; reconcile by provider identity/status or same key.
   Never blind-resend.
8. Verify rate limiting, bounded retries, provider outage, worker restart, and
   webhook outage without rolling back the source business mutation.
9. Verify suppression, privacy, owner visibility, audit, and disable/rollback.
10. Record owner acceptance. Production requires a separate authorization.

## Disable and rollback

Set `COMMUNICATIONS_DELIVERY_ENABLED=false`, stop delivery workers, retain the
durable queue and immutable evidence, keep webhook verification available long
enough to capture already-submitted outcomes, reconcile uncertain submissions,
and revoke/rotate affected provider credentials. Do not delete history, replay
uncertain work blindly, or roll back Customer/Job/financial business truth.

## Exact owner decisions

- Email provider/account and SMS provider/account.
- Preview/Production account or subaccount isolation.
- From display/address/domain, Reply-To, SMS number/sender, region, and required
  registration.
- Preview sanctioned-recipient allow-list and acceptance window.
- Transactional/operational channel defaults and fallback.
- Legal/Company consent and suppression semantics by communication purpose.
- Reminder, On My Way, arrival, completion, follow-up, renewal, reactivation,
  resend/reissue, retry, retention, and escalation policies.
- Production activation, separately and only after Preview acceptance.

No real provider, credential, sender, recipient, message, Preview change, or
Production operation is authorized by this packet.
