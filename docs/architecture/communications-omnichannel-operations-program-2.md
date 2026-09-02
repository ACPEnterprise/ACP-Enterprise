# Communications omnichannel operations

Status: non-Production engineering ready; real provider and Company policy admission remain gated.

## Authority

Business domains own business facts. Communications accepts immutable references to those facts and owns recipient resolution, eligible channel selection, versioned rendering, delivery intent, provider submission evidence, uncertainty, suppression, and history. Mobile and browser clients cannot supply arbitrary recipients or bodies and never receive provider credentials.

The operational catalog is code-versioned and fingerprinted. Exact source-event replay recovers one outbox identity; resend and follow-up require distinct governed successor identities. Provider references are evidence and never ACP logical identities. Delayed delivery cannot change Appointment, Job, Estimate, Invoice, Payment, Agreement, or Identity state.

## Message ownership and readiness

| Message | Owner | Channels | Remaining gate |
|---|---|---|---|
| Employee invitation / activation | Identity | Email | Provider |
| Appointment confirmation/reschedule/cancel | Scheduling | Email, SMS | Provider and Company channel policy |
| Appointment reminder | Scheduling | Email, SMS | Timing policy and provider |
| Technician assigned / On My Way / arrived | Dispatch | Email, SMS | Customer projection/enablement policy and provider |
| Work completed | Jobs/Field | Email, SMS | Enablement policy and provider |
| Estimate ready/decision | Estimates | Email, SMS, protected link, print | Provider; exact revision authority |
| Estimate follow-up | Estimates | Email, SMS | Cadence/limit policy and provider |
| Invoice ready | Invoicing | Email, SMS, protected link, print | Provider; exact issued revision |
| Payment receipt/status | Payments | Email, SMS, protected link, print | Accepted payment state and provider |
| Service Agreement notice | Service Agreements | Email, SMS | Notice policy and provider |

`PROTECTED_LINK` and `PRINT` describe composition channels, not provider sends. `IN_APP` is reserved for future registration and is not a fabricated Notification Center.

## Recipient, preference, and fallback

Customer destinations come from the selected Company-scoped Customer Contact. Employee destinations come from Identity invitation/User authority. The immutable intent binds the resolved destination; later Contact changes never silently redirect it. A new authorized intent is required.

Transactional eligibility, marketing consent, availability, preference, and provider suppression are separate evidence. Marketing consent never authorizes an operational message. Transactional authority does not create a marketing campaign. Selection is deterministic across catalog-allowed channels. Fallback is permitted only when the configured order, destination eligibility, transactional authority, and suppression evidence all permit it; the fallback reason is evidence.

Provider STOP/opt-out evidence creates channel suppression through an admitted signed provider event. HELP is provider/policy behavior, not implicit consent. `UNCERTAIN` requires reconciliation and is never blindly retried.

## Commercial version safety

Estimate and Invoice intents bind source event, entity identity, revision/artifact identity, and digest. A stale revision cannot be reinterpreted as current. Explicit resend of current authority creates governed delivery evidence; historical delivery remains inspectable. Delivery success or failure never changes commercial authority.

## Health and operator recovery

Administration projects distinct provider, sender/domain, SMS registration, and webhook gates. Synthetic adapters always project `DEGRADED`, never `READY`. Operators may correct authoritative contact evidence, choose another eligible configured channel, explicitly resend, inspect suppression, or wait for reconciliation. They must never blindly retry uncertain delivery.

## Threat model

Controls address cross-tenant recipient substitution, arbitrary body injection, header/HTML injection, protected-link leakage, stale commercial artifacts, provider credential exposure, webhook forgery/replay/out-of-order events, suppression bypass, STOP bypass, delivery floods, and activation-token leakage. Audit and Business Events contain IDs, classifications, digests, and safe outcomes only—never credentials, tokens, protected bodies, Payroll data, payment instruments, internal notes, or access instructions.

## Provider admission sequence

1. Owner selects provider(s) and real Company policy values.
2. Create provider accounts outside ACP; store least-privilege credentials in protected environment secret storage.
3. Configure sender identity and Reply-To; verify Email domain with provider-supplied DNS records.
4. Select SMS sender strategy, complete required US registration, and acquire a number only with owner approval.
5. Configure HTTPS callbacks and adapter-specific signature verification.
6. Enable Preview only and run deterministic synthetic-recipient acceptance for accepted, delivered, bounce, uncertainty, STOP, and history.
7. Perform a separately authorized owner-controlled real acceptance.
8. Admit Production separately. Never reuse Preview credentials or infer admission from synthetic results.

## Acceptance packet

Preview acceptance cases are: Employee invitation Email; Appointment confirmation Email/SMS; On My Way SMS; Estimate exact-revision Email/SMS; Invoice exact-revision Email/SMS; Payment receipt; bounce/failure; SMS STOP/suppression; Customer and Job history. Each must prove source ownership, recipient binding, idempotency, accepted-versus-delivered truth, safe error projection, and no cross-Company access.
