# ACP Employee — Apple owner release packet

This packet starts only after Enterprise integrates the qualified Mobile candidate. It authorizes no Apple, DNS, signing, upload, Preview, or Production mutation by itself.

## Owner execution checklist

| # | Classification | Where | Owner action | Success |
|---:|---|---|---|---|
| 1 | APPLE_ACCOUNT_REQUIRED | Apple Developer → Membership | Confirm membership is **Active** and select the intended ACP organization Team. Do not share password, MFA, recovery key, or API private key. | Intended Team is active. |
| 2 | APPLE_ACCOUNT_REQUIRED | Apple Developer → Membership details | Copy the authoritative 10-character Team ID into the owner's protected release notes. Do not put it in credentials or invent it. | Team ID is recorded for AASA/signing. |
| 3 | APPLE_ACCOUNT_REQUIRED | Certificates, Identifiers & Profiles → Identifiers | Confirm or register an explicit App ID with bundle ID `com.acpenterprise.employee`. | Exact explicit identifier exists in the intended Team. |
| 4 | APPLE_ACCOUNT_REQUIRED | That App ID → Capabilities | Enable **Associated Domains**, then save. Do not enable Push, location, camera, or unrelated capabilities. | Associated Domains is enabled. |
| 5 | OWNER_CONFIRMATION_REQUIRED | ACP DNS/HTTPS owner | Point `employee.acpenterprise.com` to approved HTTPS hosting. Do not redirect the well-known route. | Host resolves and has a trusted HTTPS certificate. |
| 6 | READY_TO_USE | Repository `mobile/` | Run `APPLE_TEAM_ID=<OWNER_TEAM_ID> npm run beta:aasa -- build/apple/apple-app-site-association`. | Extensionless JSON contains `<TEAMID>.com.acpenterprise.employee`. |
| 7 | OWNER_CONFIRMATION_REQUIRED | Approved web host | Publish those exact bytes at `https://employee.acpenterprise.com/.well-known/apple-app-site-association`; use HTTP 200, `application/json`, no redirect/authentication, and bounded public caching. | Public AASA is byte-for-byte deployed. |
| 8 | READY_TO_USE | Repository `mobile/` | Run `APPLE_TEAM_ID=<OWNER_TEAM_ID> npm run beta:aasa:verify`. | Exact URL, status, content type, cache header, redirect policy, and bytes pass. |
| 9 | OWNER_CONFIRMATION_REQUIRED | ACP web/policy owner | Approve a live ACP-controlled HTTPS support URL. | URL loads publicly and matches support operations. |
| 10 | OWNER_CONFIRMATION_REQUIRED | ACP legal/privacy owner | Approve a live ACP-controlled HTTPS privacy-policy URL. | Policy accurately covers the shipped app and loads publicly. |
| 11 | OWNER_CONFIRMATION_REQUIRED | App Store Connect → App Privacy | Map the technical evidence below to Apple's current definitions, retention, linkage, and third parties; legal/owner approves before publishing. | Complete, approved privacy answers and URL. |
| 12 | OWNER_CONFIRMATION_REQUIRED | Legal/marketing | Approve final copy, category, age-rating answers, content rights, legal entity, year, and copyright. | No placeholder remains. |
| 13 | APPLE_ACCOUNT_REQUIRED | App Store Connect → Apps → + → New App | Create `ACP Employee`, iOS, exact bundle ID, primary language, and approved SKU. Do not use a different bundle ID for Preview. | App record exists under intended Team. |
| 14 | OWNER_CONFIRMATION_REQUIRED | Internal release records | Choose one immutable SKU, for example an owner-approved internal convention; do not change it after creation. | SKU is approved and recorded. |
| 15 | APPLE_ACCOUNT_REQUIRED | Xcode automatic signing or protected EAS credentials | Create/use a valid Apple Distribution certificate and App Store provisioning profile containing Associated Domains. Never commit/export private keys into this repository. | Distribution identity/profile validate for the exact App ID. |
| 16 | APPLE_ACCOUNT_REQUIRED | App Store Connect → TestFlight → build history | Read the highest uploaded build for version `0.2.0`; reserve the next unused positive integer in release evidence. Local build `2` is not reserved because it has not been uploaded. | Unique next build is recorded. |
| 17 | APPLE_ACCOUNT_REQUIRED | Owner release approval | Explicitly authorize signing of the qualified Preview source SHA/build only. | Signed archive uses Preview, exact bundle ID, reserved build, and intended Team. |
| 18 | APPLE_ACCOUNT_REQUIRED | Owner release approval | Separately authorize upload after archive validation. | Uploaded build enters App Store Connect processing; no Production traffic. |
| 19 | APPLE_ACCOUNT_REQUIRED | App Store Connect → TestFlight → Internal Testing | Create/choose an approved internal group, add the processed build, and run the physical acceptance packet with synthetic Preview data. | Approved internal tester installs and accepts the build. |
| 20 | APPLE_ACCOUNT_REQUIRED | App Store Connect → TestFlight → External Testing | Only if desired, create an external group, complete beta metadata/review credentials, and submit the build for TestFlight beta review. | Apple approves external testing before invitations. |

## AASA owner packet

From the integrated repository:

```sh
cd mobile
APPLE_TEAM_ID=<OWNER_TEAM_ID> npm run beta:aasa -- build/apple/apple-app-site-association
APPLE_TEAM_ID=<OWNER_TEAM_ID> npm run beta:aasa:verify
```

The generated `appID` is `<APPLE_TEAM_ID>.com.acpenterprise.employee`. Only `/activate` and `/activate/*` are eligible. The static document contains no activation token or secret. The verifier fails closed without a valid Team ID and rejects a redirect, non-200 response, wrong content type, missing cache policy, changed URL, or changed bytes.

## App Store metadata review

| Field | Draft/value | Classification |
|---|---|---|
| Name | ACP Employee | READY_TO_USE |
| Bundle ID | `com.acpenterprise.employee` | READY_TO_USE |
| Version/build | `0.2.0` / local candidate `2`; reserve next unused build before upload | OWNER_CONFIRMATION_REQUIRED |
| Subtitle | Your ACP workday | OWNER_CONFIRMATION_REQUIRED |
| Description | Secure employee access to assigned work, Job detail, own Timekeeping/My Time, and permission-derived own-data capabilities from ACP Enterprise. | OWNER_CONFIRMATION_REQUIRED |
| Beta description | Validate activation/sign-in, session restoration, My Day, assigned Job, Timeclock/My Time, stale/offline recovery, and logout against synthetic ACP Preview data. | OWNER_CONFIRMATION_REQUIRED |
| Review notes | No public registration. Apple receives a bounded synthetic Preview review account through protected review fields. Directions explicitly open system Maps; no device-location tracking, payment collection, or arbitrary customer messaging. | OWNER_CONFIRMATION_REQUIRED |
| Primary category | Business | OWNER_CONFIRMATION_REQUIRED |
| Support URL | `OWNER_REQUIRED_LIVE_HTTPS_URL` | OWNER_CONFIRMATION_REQUIRED |
| Privacy URL | `OWNER_REQUIRED_LIVE_HTTPS_URL` | OWNER_CONFIRMATION_REQUIRED |
| Copyright | `OWNER_REQUIRED_LEGAL_ENTITY_AND_YEAR` | OWNER_CONFIRMATION_REQUIRED |
| SKU | `OWNER_REQUIRED_IMMUTABLE_SKU` | OWNER_CONFIRMATION_REQUIRED |
| App record entry | Name, primary language, bundle ID, SKU, category | APPLE_ACCOUNT_REQUIRED |

Age-rating inputs for owner review: authenticated workforce utility; no gambling, unrestricted web access, public social feed, simulated gambling, contests, or in-app user-to-user communication was identified. Job/customer work descriptions are server-owned operational content. The owner must answer Apple's current questionnaire from actual accepted content and regions rather than treating this as a legal conclusion.

Internal tester focus: confirm **PREVIEW** in Account; use only a sanctioned synthetic identity; verify sign-in/session, My Day, assigned Job, Timeclock/My Time, reconnection, authoritative lost-response recovery, and logout; stop if Production or real protected data appears.

## Privacy owner/legal review

“Processed” below means the current app accesses the data for its function. Apple's meaning of “collected,” linkage, retention, and third-party processing remains an owner/legal determination.

| Apple-oriented category | Observed behavior | Persisted locally | Identity-linked | Tracking | Confidence/source | Decision |
|---|---|---|---|---|---|---|
| Contact info — email/login identity | Submitted to ACP authentication and shown in Account. | Session repository stores accepted session material in OS SecureStore; password is never stored. | Yes | No | HIGH: auth coordinator, Account, SecureStore | OWNER_CONFIRMATION_REQUIRED |
| User ID / account identity | ACP User→Membership→Employee self-resolution and permission context. | Authenticated application state; session secret in SecureStore. | Yes | No | HIGH: auth/authorization clients | OWNER_CONFIRMATION_REQUIRED |
| Customer/Job work data | Narrow assigned-work projection includes customer display name, bounded service address, Appointment/Job status and evidence. | Last-confirmed UI memory only; no general business-data database. | Linked to employee work context | No | HIGH: Employee Operations/Field clients | OWNER_CONFIRMATION_REQUIRED |
| Other financial information | Permission-gated own pay-statement status/artifact may be fetched; no payment instrument, banking entry, or Payroll administration. | Artifact uses an incognito/non-caching, JavaScript-disabled WebView and is not placed in general storage. | Yes | No | HIGH: My Pay client/screen | OWNER_CONFIRMATION_REQUIRED |
| Diagnostics | Safe request correlation, app version/build, environment and recovery classification may be sent to ACP. No third-party crash/analytics SDK exists. | Ordinary process/log lifecycle; sanitizer excludes protected fields. | Potentially through authenticated request context | No | HIGH: API client/safe logger | OWNER_CONFIRMATION_REQUIRED |
| Usage data | No analytics/event SDK or usage stream identified. | No | No app collection identified | No | HIGH: dependency/source inventory | OWNER_CONFIRMATION_REQUIRED for server access-log interpretation |
| Location | No device location API/permission. User-initiated Maps handoff uses an already-authorized service address. | No device-location history | No device-location collection | No | HIGH: Info.plist and Job Workspace | READY_TO_USE technical evidence; legal confirms |
| Contacts | No Contacts API/permission. | No | No | No | HIGH: native/source inventory | READY_TO_USE technical evidence; legal confirms |
| Photos/camera/microphone | No accepted capture/upload feature and no corresponding permission. | No | No | No | HIGH: native/source inventory | READY_TO_USE technical evidence; reassess before enabling |
| Device identifiers | No advertising ID or app-level device identifier collection identified. | No | No app collection identified | No | HIGH: dependency/source inventory | OWNER_CONFIRMATION_REQUIRED for infrastructure interpretation |

The owner/legal reviewer must also confirm ACP server retention, access logs, subprocessors, privacy-policy wording, and whether Apple's definitions treat authenticated server processing as collection. App privacy answers cover the shipped app and integrated third-party code, not merely what Mobile persists locally.

## Enterprise handoff

- Source candidate: `work/laptop1-phone-20260912` at `bf28a61cfe7d36d0b050e0118b21b234c8a555e3`.
- Owner-packet branch: `work/mobile-apple-owner-release-packet-1`.
- Integrate only after confirming current authority has no overlapping Mobile release changes.
- Run `npm run apple:release:qualify` from `mobile/`; expected output is a clean locked install and unsigned Preview archive.
- Signing proof: qualification must report the `.app` is unsigned; no certificate, profile, private key, Apple credential, or upload artifact belongs in Git.
- Environment proof: archive contains the exact Preview API, embedded JS bundle, inactive `.invalid` Production configuration, and no Metro/LAN API dependency.
- Native environment proof: dynamic Expo configuration writes `preview`, the exact Preview API, and `productionActivated=false` into the archived Expo constants manifest; archive qualification rejects any mismatch.
- Runtime/backend/schema/Preview deployment changes: none.
- Owner checklist: this file. Machine contracts remain under `mobile/operations/`.
