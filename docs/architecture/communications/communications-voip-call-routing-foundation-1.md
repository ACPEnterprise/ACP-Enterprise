# COMMUNICATIONS.1 — VoIP and Call Routing Foundation

Status: `ARCHITECTURE_DEFINED`

## Purpose

Define a provider-neutral call and routing authority that can connect a
business or campaign number to an office CSR workflow without becoming a
second Lead, Customer, Scheduling, or Job system.

`business/tracking number -> inbound call -> office CSR desktop -> Customer/prospect match -> Lead create/attach -> source/campaign attribution -> Job/Appointment booking`

After-hours routing may forward to a cell, but forwarding is delivery state,
not proof that a call was answered, qualified, or booked.

## Routing model

- Office hours route to the authenticated CSR queue.
- After-hours route to an approved fallback destination or voicemail.
- Overflow/no-answer creates a durable callback task or voicemail evidence.
- Campaign tracking numbers identify source/campaign evidence only.
- A CSR may search for a possible Customer/prospect match; fuzzy similarity cannot establish identity.
- A legitimate service opportunity creates or attaches a Pipeline Lead through the canonical Pipeline contract.
- Booking uses Scheduling/Appointment authority; Communications does not create parallel appointment state.

## Provider-neutral boundary

The future adapter must expose number identity, call/session identity,
direction, timestamps, routing state, answer/voicemail outcome, disposition,
consent state, and an evidence digest. Carrier/SIP/telephony selection is
deferred. No provider is selected by this milestone.

Future call recording and transcription are optional provider-gated adapters;
they are not required for the foundation and must remain disabled until
consent, retention, access, and jurisdiction policy are approved.

## Privacy, permissions, and events

- CSR access is Company/Branch/queue scoped.
- Campaign attribution is readable only where the user can access the related Company/Branch evidence.
- Call metadata is minimized; recordings/transcripts require explicit consent and retention policy.
- Business Events record call intake, routing, answer/voicemail outcome, disposition, Lead create/attach, and booking handoff.
- No raw credentials, unrestricted recordings, or hidden provider payloads are exposed to LIA or the Command Center.

## Acceptance criteria

1. A business number routes to the office CSR queue during office hours.
2. After-hours, overflow, and no-answer behavior is deterministic and observable.
3. A tracking number preserves source/campaign identity without asserting Customer identity.
4. CSR can create or attach one Lead idempotently after disposition.
5. Exact Customer/prospect matching, Branch scope, and authorization are enforced.
6. Qualified Leads can hand off to Scheduling/Appointment authority without duplicated state.
7. Voicemail and callback evidence are visible with freshness and limitations.
8. Recording/transcription remains unavailable until consent and provider gates pass.
9. Owner can approve routing hours, destinations, queue policy, numbers, and retention before activation.

## Explicit gates

- HUMAN_GATE: office hours, fallback destination, queue ownership, consent, and retention policy.
- PROVIDER_GATE: carrier/VoIP account, numbers, routing, recording, transcription, and delivery reliability.
- SOURCE_DOMAIN_GATE: canonical Customer matching, Pipeline Lead disposition, and Scheduling booking contracts.
