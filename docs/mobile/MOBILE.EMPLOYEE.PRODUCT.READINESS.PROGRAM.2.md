# ACP Employee product-readiness program 2

ACP Employee remains a Preview-only client of ACP Enterprise. This program upgrades the accepted native application to Expo SDK 57 / React Native 0.86, raises the required iOS floor from 15.1 to 16.4, and preserves the existing bundle identity. Production stays inactive and no backend or schema authority is added.

## Capability and ownership audit

| Area | Classification | Accepted boundary |
|---|---|---|
| Authentication, activation, SecureStore, logout | AUTHORITATIVE | Server session is verified before UI authority; foreground revalidation removes stale navigation after permission, Branch, Membership, authorization-version, or credential-version change. |
| My Day and Job Workspace | AUTHORITATIVE | Own-day projection plus bounded customer/location and assigned-job field projection. Server ordering and ownership win. |
| Timeclock and My Time | AUTHORITATIVE | Server time, self-resolution, idempotency, state refresh, breaks, corrections, provenance, and stale-action disabling. |
| My Pay | AUTHORITATIVE | Own Payroll status/statements and protected in-memory artifact only; no Employee selector, rates, banking, tax, or Payroll administration. |
| Field travel/evidence/handoff | AUTHORITATIVE | En route/arrival, work-performed evidence, customer disposition, readiness, and invoice-handoff refresh are permission- and assignment-scoped. |
| Job start/pause/resume/complete | SERVER_REQUIRED | Existing general Job command responses are administrative rather than a narrow employee-safe projection. Mobile must not filter them locally. |
| Photos/attachments | SERVER_REQUIRED | No accepted assignment-owned upload/custody contract exists. A future contract needs content/type/size limits, malware handling, EXIF stripping, object custody, idempotency, and assignment authorization. |
| Customer signature | SERVER_REQUIRED | No accepted customer-signature evidence authority exists. Require assignment ownership, signer/disclosure evidence, immutable artifact digest, revocation/correction semantics, and explicit consent UX. |
| Estimate/Agreement detail | SERVER_REQUIRED | Administrative projections are too broad. Field-safe read projections must explicitly omit internal cost, margin, office notes, and unrelated customer history. |
| Invoice/payment | PARTIAL | Field-safe handoff status is authoritative. Payment execution and administrative invoice detail remain absent by design. |
| Push notifications | ACTIVE_OWNER_COLLISION | Communications owns provider/server/APNs authority. Mobile requests no notification permission until an accepted channel and payload-minimization contract exists. |
| Apple distribution | APPLE_GATE | Developer/App Store Connect authority, registered App ID/capabilities, credentials/profile, live AASA, archive/upload, and TestFlight authorization remain external. |

Unknown additive response fields are stripped by the mobile schemas, while missing or incompatible required fields fail safely. HTTP requests carry a fresh opaque `X-Request-ID`; only the safe response correlation identifier and recovery classification may reach diagnostics.

## Failure and lifecycle acceptance

The recovery vocabulary is `RETRY_SAFE`, `RETRY_AFTER_REFRESH`, `USER_CORRECTION_REQUIRED`, `OWNER_ADMIN_ACTION_REQUIRED`, `RECONCILIATION_REQUIRED`, `TEMPORARILY_UNAVAILABLE`, and `TERMINAL_FAILURE`. It guides copy and support diagnostics but never authorizes a retry. Mutation retries remain operation-specific and idempotent.

Cold launch verifies protected session state. Foreground/device-unlock revalidates session, Company/Branch context, Employee qualification, and current capabilities before returning to the authorized shell. A rejected or revoked session clears protected session material. Read surfaces retain only in-memory last-confirmed projections and label them stale; mutation controls are disabled outside known authoritative ready state. The permanent regression covers a 502 after confirmed My Day/My Time data, stale rendering, disabled punch, recovery, and no duplicate operation.

Physical revocation rehearsals, to run only under an Enterprise-approved Preview window:

1. Remove `COMPANY_TIMEKEEPING_OWN_PUNCH`, advance authorization version, foreground the app, verify punch controls disappear and direct API returns 403; restore and revalidate.
2. Remove the synthetic Branch grant, advance authorization version, foreground, verify My Day/Job data disappears with no cross-Branch cache access; restore and revalidate.
3. Deactivate the synthetic Membership, foreground, verify the app returns to authentication/restricted state and exposes no cached protected screens; reactivate and require accepted reauthentication.

## Deterministic Job fixture contract

Enterprise/OM1 may provision only after a safe Preview window using the repository beta-fixture plan and a synthetic `.invalid` login. Create one marked synthetic Company Membership, one Branch grant, one Employee, own-time/My-Day/Job permissions, timezone, synthetic Customer and Service Location, one Job, one Appointment, and one active primary assignment. Add no compensation, Payroll configuration, payment, bank, tax, real-looking identity, or QBO evidence. The fixture command must be idempotent, detect contradictory keys, and provide domain-safe reset. This enables the field-day sequence: sign in → My Day → assigned Job → en route → arrived → work evidence → customer disposition → handoff readiness → time punches. Start/pause/resume/complete stay blocked until the narrow server contract above exists.

## Persona and real-employee acceptance

- Restricted/OWN_DATA_ROLE: coherent My Day, My Time, optional My Pay, and Account only as granted.
- Technician: adds assigned Job field surfaces and execute controls only with `COMPANY_JOB_READ` / `COMPANY_JOB_EXECUTE`.
- Dispatcher, CSR, and office manager: no office/admin mobile surfaces are inferred; use ACP Employee only when explicit self/field permissions make it useful.
- Future Lianne acceptance: issue the real invitation only through the accepted onboarding owner, activate directly, verify Membership → Employee → Branch, inspect permission-derived tabs and direct denials, revalidate revocation, and logout. No email or identity is encoded here.

Every future Employee checklist covers activation/login, Branch context, visible surfaces, direct API denials, own-data isolation, offline/stale behavior, session restoration, permission/Branch/Membership revocation, and logout purge.

## Physical evidence packet

Owner-observed iPhone 13 Pro Max evidence already establishes: Preview sign-in; User → Membership → Employee; explicit Branch scope; My Day, My Time, and Account; restricted navigation; safe stale state during a transient 502; mutation disabled while stale; automatic recovery; one synthetic Clock In and Clock Out; one completed one-minute interval; and no duplicate punch. This text record intentionally contains no credentials, activation references, employee/customer payloads, or protected screenshots.

The upgraded build may replace the existing app only after tests, Hermes exports, Pods, unsigned native builds, and signing qualification succeed. Reinstallation is not required merely to manufacture evidence, and no additional punch or Preview revocation is authorized by this program.

## Apple and privacy boundary

The app requests no camera, photo library, location, contacts, microphone, background location, advertising tracking, or notification permission. Maps is an explicit external HTTPS handoff. The privacy shield covers app-switcher snapshots; SecureStore contains session material only; pay artifacts remain memory-only with WebView JavaScript, DOM storage, cookies, and caching disabled.

Release identity is ACP Employee 0.2.0 build 2, bundle `com.acpenterprise.employee`, Preview channel, and contract compatibility metadata. A signed TestFlight successor requires Apple team authority, registered Associated Domains, live AASA, valid signing/provisioning, App Store Connect metadata/privacy answers, archive validation, upload authorization, and an approved synthetic Preview acceptance window.
