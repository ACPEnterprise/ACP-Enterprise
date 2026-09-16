# LIA conversational voice read-only boundary

## Authority and architecture

Voice is an input/output adapter around the existing `/api/v1/lia/ask` contract.
Recognized text follows the same planner, governed retrieval, Company and Branch
scope, evidence digest, authorization version, stale detection, action refusal,
and navigation suggestions as typed text. Voice has no database adapter, command
bus, tool executor, or separate intelligence state.

The web implementation uses the browser's foreground Web Speech recognition and
speech synthesis capabilities. ACP does not persist raw audio. A transcript is
placed into the normal editable question field; only explicitly enabled
conversation mode submits it automatically. Conversation mode is visibly active,
has an End Conversation control, stops on page cleanup, and expires after 90
seconds of inactivity. Speech output can be interrupted and replayed.

Deployment permits microphone use only by the same-origin ACP page. Camera and
geolocation remain disabled. Browser permission is still required and denial
fails safely.

## State model

`IDLE → LISTENING → TRANSCRIBING → THINKING → SPEAKING` with explicit
`INTERRUPTED` and `ERROR` states. Browser speech-end detection receives a 900 ms
pause tolerance before stopping capture. Manual Stop and Cancel remain available.
No hidden/background capture or wake-word listener exists.

## Context and navigation

Voice uses the existing in-memory `conversation_id`, subject identity,
authorization version, evidence digest, as-of time, and topic domains. Domain-only
screen context is supported for Payroll, Scheduling, Dispatch, Financial Reports,
Luminary, Beacon, and Price Book; entity screens continue to pass opaque UUIDs.
The server reauthorizes every retrieval.

Navigation occurs only when a navigation utterance matches a route returned in
the authorized LIA response. Client text cannot manufacture a destination.
Navigation changes UI route only and never mutates business data.

## Spoken answers

The full response and evidence remain visible. Speech defaults to the direct
conclusion, one important implication, and the safe next action. Evidence details
are not read aloud automatically. Follow-up questions such as “Why?” and “What
evidence?” travel through ordinary LIA context and retrieval.

## Future action boundary

Voice recognizes these non-executing categories for safety qualification:

- `READ`
- `NAVIGATE`
- `LOW_IMPACT_WRITE`
- `HIGH_IMPACT_WRITE`
- `MONEY`
- `PAYROLL`
- `EMPLOYMENT`
- `PRICING`
- `ACCOUNTING`

Current runtime supports only `READ` and server-authorized `NAVIGATE`. Mutation
phrasing may be classified for refusal but is still sent to governed LIA, which
returns the existing non-executing policy response. No proposal approval or domain
execution is connected.

A future confirmation must bind exact action, target, requested value, current
version/evidence digest, principal, Company/Branch scope, permission, risk,
expiration, and idempotency identity. Confirmation would authorize preparation,
not execution, until separately approved domain tooling exists.

## Apple and iPhone findings

Current protected authority does not contain the ACP Employee native workspace.
Qualified remote Mobile branches contain React Native and native iOS projects,
but they remain outside protected authority and under Mobile ownership. Therefore
this candidate does not copy or independently modify them.

The protected application has no Apple Speech integration, `AVAudioSession`
voice configuration, speech/microphone usage descriptions, Siri/App Intents
extension, App Shortcut, or Action Button contract. Adding those safely requires
the Mobile successor to become authoritative and an Apple entitlement/signing
lane. Siri must open the authenticated ACP experience whenever the device is
locked or protected evidence cannot be safely returned.

A foreground wake phrase is not implemented. Browser speech recognition is not a
reliable on-device wake-word engine, and continuous listening solely to detect
“LIA” would violate the no-hidden/background-microphone boundary. Explicit
Conversation Mode provides the safe foreground hands-free boundary.

## Retention and degraded behavior

Voice adds no transcript persistence. Recognized text follows the unresolved
existing conversation-retention policy and remains in component memory for the
active page. Ordinary logs receive only the same safe LIA request metadata; raw
audio is never logged.

Speech recognition network failure does not call LIA. LIA network failure retains
the editable transcript and shows the existing fail-closed request state. Cached
answers are not substituted for current authoritative evidence.

## Physical acceptance

1. Open authenticated Preview `/lia` on desktop and iPhone Safari.
2. Grant microphone permission while the visible Voice conversation panel is open.
3. Tap **Listen**, say “Show me Lianne Hernandez,” stop, edit if necessary, and send.
4. Confirm the same authoritative response and evidence as typed LIA.
5. Start Conversation Mode and ask “Is she payroll ready?” then “What should I do next?”
6. During speech, tap **Interrupt LIA**, say “Just tell me what I need to do,” and confirm the Employee referent remains bound.
7. Ask “What is scheduled tomorrow?” and “Who is assigned?”
8. Say “Open Dispatch”; confirm navigation occurs only after authorized Dispatch evidence supplies that route.
9. Ask “Show me the May P&L” and “Is that QuickBooks or ACP?” Verify source authority remains explicit and no figures are invented.
10. Ask “What does Luminary know?” and “What needs my attention?”
11. Say “Move that appointment.” Verify policy refusal and zero mutation.
12. Disconnect the network and retry. Verify no cached business answer is presented as current.
13. End Conversation and verify the microphone indicator stops.
14. Leave/reopen the page and verify no voice transcript is restored.
