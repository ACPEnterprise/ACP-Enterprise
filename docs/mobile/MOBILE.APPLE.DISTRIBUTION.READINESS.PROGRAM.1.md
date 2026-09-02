# MOBILE.APPLE.DISTRIBUTION.READINESS.PROGRAM.1

## Release classification

ACP Employee is locally ready for owner Apple distribution action. Engineering identity is `ACP Employee`, bundle `com.acpenterprise.employee`, version `0.2.0`, local candidate build `2`, iPhone-only, portrait, minimum iOS 16.4. The candidate has not been uploaded and does not reserve an App Store build number.

| Area | Classification | Evidence/action |
|---|---|---|
| Bundle, display identity, Release compile, workspace/scheme | READY | Repository and unsigned archive preflight |
| Preview beta environment | READY | `beta` profile pins ACP Preview; Production is invalid/inactive |
| Icon/launch assets | READY | Opaque 1024x1024 icon; native launch storyboard |
| Privacy manifest/permissions | READY | Tracking false; required-reason APIs aggregated; no gated permissions |
| Associated Domains/AASA template | READY locally | Live hosting is DNS_REQUIRED |
| Development device signing | READY | Local Development identity/profile observed; no material inspected or changed |
| Distribution signing | SIGNING_REQUIRED | No Distribution identity was observed |
| App identifier/capabilities | OWNER_APPLE_ACTION_REQUIRED | Confirm/register exact identifier and Associated Domains in owner Team |
| App Store Connect record/metadata/privacy | APP_STORE_CONNECT_REQUIRED | Owner-controlled creation/submission |
| Archive/upload/TestFlight | OWNER_APPLE_ACTION_REQUIRED | Unsigned archive qualifies; distributable archive/upload prohibited here |

## Version and environment policy

Marketing version changes only for an owner-approved product release train. Every uploaded build within that version uses a strictly increasing integer. Immediately before an authenticated build, read the latest App Store Connect build and reserve the next integer in repository evidence; never reuse an uploaded number. Build `2` is a local candidate only.

Bundle identity is independent from runtime environment. The `beta` store profile is Preview-only. Runtime schema accepts development/preview/production but requires exact Preview URL for Preview and explicit activation plus HTTPS for Production. The current Production profile uses an `.invalid` placeholder and activation false. Unknown/mismatched configuration fails closed.

## Universal Links and AASA

Entitlement: `applinks:employee.acpenterprise.com`.

Publish the generated extensionless document at `https://employee.acpenterprise.com/.well-known/apple-app-site-association` with HTTP 200, `Content-Type: application/json`, no authentication, no redirect or content transformation, and a bounded public cache policy. Generate with `APPLE_TEAM_ID=<authoritative-team-id> npm run beta:aasa`. Validate exact bytes and SHA-256 after deployment. Allowed components remain `/activate` and `/activate/*` only. The invitation token is never part of static AASA content.

Universal/custom links provide routing only. Activation validates the exact HTTPS host/custom scheme and path, holds the invitation transiently, then calls server onboarding authority. Future Job/Estimate/Invoice links must restore session, refresh current permission/Branch/assignment state, and fail closed for stale or foreign identifiers.

## Privacy disclosure evidence

The app processes login identity, ACP session, own Employee/Membership/Branch/capabilities, assigned work, Customer display and bounded service address, Job/Appointment evidence, own Timekeeping, and—only when permission allows—own Payroll statement/status. Session secrets use OS-protected storage; ordinary business evidence is held in application memory/last-confirmed UI, not a parallel business database. Data is sent to ACP Preview APIs over HTTPS. No advertising, tracking, third-party analytics, background location, contacts, microphone, camera, photo library, push registration, or payment provider exists in this release.

App Store privacy answers require owner/legal confirmation of Apple's definitions, linkage and retention, but technical evidence supports: no tracking; no advertising; no third-party analytics; account/work/location-address/time/pay-statement data is processed solely for authenticated ACP functionality. Future photos and notifications require a fresh disclosure review before enabling permissions.

## Future permissions

- Photos: after an accepted artifact contract, add `NSCameraUsageDescription` for Job/equipment evidence capture. Prefer PHPicker/limited selection so broad photo-library access is unnecessary; add `NSPhotoLibraryUsageDescription` only if the implemented workflow genuinely needs it.
- Notifications: after accepted Employee notification/token authority, enable Push Notifications/App ID capability, `aps-environment` through the signing profile, APNs key/certificate under protected provider custody, and runtime permission request with minimum lock-screen content.
- Do not add location, contacts, microphone, Bluetooth or background modes for either feature.

## Export compliance

The current app uses standard HTTPS and OS-protected credential storage; no custom cryptographic implementation or encryption product was identified. Apple will still ask export-compliance questions. The owner should answer from Apple's then-current wording with legal/compliance review; repository evidence must not substitute for a legal determination. Do not set `ITSAppUsesNonExemptEncryption` until that answer is confirmed.

## App Store metadata packet

Owner decisions are required for final marketing copy. Required facts/checklist:

- Name: `ACP Employee`; subtitle and keywords: owner marketing approval required.
- Description: authenticated employee field operations, own Timekeeping, assigned Jobs, and own-data capabilities; do not promise gated photos/notifications/commercial tools.
- Primary category: owner decision (likely Business, subject to store taxonomy review).
- Support URL and privacy-policy URL: must be live ACP-controlled HTTPS pages before submission.
- Marketing URL: optional owner decision.
- Age-rating questionnaire: answer from actual field/work content; no unrestricted web, gambling, or user-generated public feed exists.
- Copyright, review contact, support contact, privacy contact: owner-supplied organizational details.
- Screenshots and review notes: synthetic Preview content only.

## Screenshot plan

Capture clean synthetic Preview evidence on Apple-required current screenshot sizes. Minimum story: Sign In; My Day with synthetic assignment; Job Workspace with bounded Customer/Location; authoritative field readiness; My Time; Account/Preview identity. Include a small iPhone class and current large class for layout qualification; produce required App Store screenshot dimensions from an accepted simulator/device matrix. No credentials, invitation tokens, real Employee/Customer data, Payroll value, internal IDs, or system status-bar surprises.

## Review account and notes

Create later through sanctioned Preview fixture tooling: one revocable synthetic User→Membership→Employee, one Branch, Technician permissions, one synthetic assigned Job, and Timekeeping configuration. Never share owner/admin credentials. Keep activation/sign-in instructions in App Review notes, rotate/revoke after review, and identify that there is no public self-registration.

Draft review note: ACP Employee requires an ACP-issued invitation/account. Review credentials access synthetic Preview data only. The app shows assigned employee work and own Timekeeping; Job actions are server-authorized. Directions open the system map explicitly and the app does not track location. Payment collection and arbitrary Customer messaging are absent. Provide the support contact and any time-sensitive fixture steps immediately before submission.

## TestFlight runbooks

### Internal

1. Confirm Apple membership, agreements, Team, App ID/Associated Domains, live AASA, App Store Connect record and privacy metadata.
2. Read latest uploaded build number; reserve next build; run clean preflight.
3. Establish owner-controlled Distribution signing, archive Release Preview build, validate, upload, answer export compliance, and wait for processing.
4. Assign only approved internal tester group; install; execute Physical iPhone Acceptance V2; review crashes/feedback; record acceptance or withdraw build. TestFlight builds expire after Apple's current retention window.

### External

External testing additionally requires beta App Review, public beta description/feedback contact, review credentials, compliance completion, and approved tester/group controls. Do not assume internal approval grants external distribution.

## Physical acceptance V2

After protected integration and a sanctioned synthetic Job: verify build/version/Preview, session restoration, My Day, assigned Job, Job details, On My Way, Arrive, Start, evidence, pause/resume, completion blockers, Complete, Invoice handoff, stale/offline recovery, permission revocation, logout/re-login, and zero Production traffic. Do not repeat already-proven Timekeeping punches merely for evidence.

## Diagnostics, logging and network

No third-party crash provider is present. Use Xcode/TestFlight organizer crash evidence plus ACP-safe request correlations. Release diagnostics may contain environment, app version/build, route class, recovery class and opaque correlation only. Never include passwords, tokens, invitation secrets, login identity, Customer/Employee payloads, addresses, notes, Payroll/financial values, or provider material.

All accepted remote APIs use HTTPS. ATS arbitrary loads are disabled. Local-network allowance supports the explicit development profile only and does not select a runtime endpoint; store beta is compiled with the exact Preview HTTPS endpoint. Production remains inactive.

## Rollback and compatibility

Bad TestFlight build: remove it from tester groups, preserve evidence, fix, allocate a higher build number, requalify and upload successor. Installed older builds cannot be remotely removed; server backward compatibility and authorization remain decisive. AASA rollback restores the last accepted exact bytes. Session recovery is logout/re-authentication. The current compatibility header/version permits server diagnostics, but forced minimum version is policy-gated; until accepted, incompatible required contracts must fail clearly while preserving sign-out.

Before every backend integration, run Mobile contract tests against additive/non-breaking response behavior. Removing/renaming required fields or changing authorization/failure semantics requires coordinated client compatibility evidence. Production activation requires a separately approved real HTTPS endpoint, Production permission/identity/privacy review, build profile activation, server compatibility qualification, and explicit owner release authority.

## Release security threat model

- Stolen session: OS-protected storage, server verification/revocation, logout purge, foreground revalidation.
- Stale build: compatibility diagnostics, safe malformed-response handling, future minimum-version policy.
- Deep-link attack: trusted host/path, transient invitation, server validation, no link-as-authorization.
- Bundle tampering: rely on Apple code signing/distribution; no embedded server/provider secret.
- Debug leakage: Preview compile pin, Production fail-closed, no test identity or localhost in candidate archive.
- Review account abuse: least privilege, synthetic data, revocable and monitored server authority.
- Screenshots/app switcher: PrivacyShield and synthetic screenshot policy.
- Notification privacy: feature absent; future payload minimum necessary.
- Server incompatibility: coordinated contract qualification and safe failure.

## Owner Apple action packet

1. **Apple Developer website → Membership:** confirm membership is Active and the intended ACP Team is selected. Needed: organizational owner access. Never share password, MFA code, recovery key or private key. Success: active Team and visible Team ID.
2. **Certificates, Identifiers & Profiles → Identifiers:** register/confirm explicit App ID `com.acpenterprise.employee`; enable Associated Domains. Never share certificate private keys. Success: exact identifier under intended Team with capability enabled.
3. **ACP DNS/HTTPS hosting:** point `employee.acpenterprise.com` to approved hosting and serve exact generated AASA at the well-known path. Needed: authoritative Team ID. Success: public HTTPS 200 JSON, no redirect/auth, bytes/digest match.
4. **App Store Connect → My Apps:** create `ACP Employee` using the exact bundle ID and owner-selected SKU/primary language. Do not paste credentials into repository. Success: app record exists under intended Team.
5. **App Information/Privacy/Pricing:** enter owner-approved support/privacy URLs, category, age rating, privacy answers, availability and review contacts. Success: no incomplete required metadata for TestFlight review.
6. **Signing:** choose owner-managed EAS credentials for repeatable release, or Xcode automatic signing for the first controlled archive. Authorize creation/use only while physically present. Success: valid Apple Distribution certificate/profile with Associated Domains; secrets remain in Apple/EAS protected custody.
7. **Build:** reserve next build number, run repository preflight, create signed Release Preview archive, validate. Success: Organizer/EAS reports a valid distributable archive for `com.acpenterprise.employee` and Preview.
8. **Upload/TestFlight:** separately authorize upload, answer compliance, await processing, assign approved internal group. Success: processed build installable by approved internal tester—no Production traffic.

## Protected automation readiness

Future CI can run clean install, Expo checks, tests, Hermes, Pods, unsigned archive preflight, version reservation validation, secret scan, then authenticated EAS/Xcode build/upload. Credentials must use owner-controlled protected secret storage with environment approval, least privilege, audit, rotation and no fork/untrusted-PR exposure. Promotion from build to internal/external TestFlight remains an explicit owner-controlled action.
