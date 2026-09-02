# ACP Employee module completion

ACP Employee is a Preview-pinned Expo/React Native client of ACP Enterprise. This milestone completes every current employee-safe contract without adding parallel authority.

## Product boundary

- Authentication: invitation activation, credential establishment, verified secure-session restoration, Membership/Employee resolution, permission-derived navigation, authorization-version rejection, logout, and protected background state.
- Work: server-ordered My Day, bounded Customer/Service Location projection, assigned Job Workspace, external Maps handoff, and explicit stale/reassignment handling.
- Field evidence: authoritative itinerary and assignment ownership, travel/arrival state, work-performed summary, customer disposition, completion-readiness evidence, and invoice-handoff refresh. Every mutation uses an opaque idempotency key, disables duplicate action, refuses offline success, and rehydrates server truth.
- Time: server-authoritative punch transitions and My Time evidence remain independent of Job state.
- My Pay: `/api/v1/payroll/me/payroll-status`, own statement history, correction/YTD/payment metadata, and authenticated HTML artifact retrieval. Artifacts stay in memory, are rendered with JavaScript, DOM storage, cookies, and cache disabled, and are cleared when the viewer closes. No Employee ID, rates, tax, bank, other-employee data, or Payroll administration is exposed.

Broad Job start/complete commands are intentionally absent: their current administrative response contracts are not a narrow employee-safe projection. Mobile does not filter broad server payloads locally.

## Failure and privacy model

Loading, empty, forbidden, identity-not-ready, expired-session, offline/stale, conflict, malformed-response, and unavailable states remain distinct. Read caches are memory-only and explicitly stale; mutations never queue or claim success offline. SecureStore remains limited to session material. The application requests no location, contacts, camera, microphone, advertising, or background-tracking capability.

## Preview qualification and external gate

Beta remains fixed to `https://preview.allcountyhomeservices.com`; Production is structurally inactive and fail-closed. The deterministic synthetic fixture contract now includes Time, My Day, field evidence, own-pay-statement permission, corrected statement, and unavailable-YTD scenarios. Actual Preview mutation still requires separate fixture authorization and an owner-supplied synthetic login.

Signed distribution remains externally gated by an active Apple Developer team, authoritative Team ID, App ID/Associated Domains registration, live AASA hosting, App Store Connect record, credentials/provisioning, and upload authorization. No Apple secret belongs in the repository.
