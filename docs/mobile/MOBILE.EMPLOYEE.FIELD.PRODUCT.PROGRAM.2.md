# MOBILE.EMPLOYEE.FIELD.PRODUCT.PROGRAM.2

## Authority and product boundary

This packet reconciles the authoritative Field Program 1 lineage with the later Expo 57 and Mobile product-readiness lineage. ACP Employee remains a Preview-only client of ACP Enterprise. Employee, Company, Branch, Job, Dispatch, Timekeeping, commercial, Asset, Communications, and authorization truth remains server-owned.

## Current capability matrix

| Capability | Classification | Current source/boundary |
|---|---|---|
| Authentication, session, Branch and permission reconciliation | AUTHORITATIVE | Identity/AuthZ session and Employee qualification |
| My Day and assigned itinerary | AUTHORITATIVE | `/employee-operations/me/day`, `/technician/itinerary` |
| Assignment-safe Job detail | AUTHORITATIVE | Employee My Day projection and `/technician/jobs/{job_id}` |
| On My Way and Arrived | AUTHORITATIVE | Versioned Dispatch assignment arrival command |
| Start, pause, resume and complete | AUTHORITATIVE | Versioned Job lifecycle commands, assignment-gated Mobile UX |
| Work summary and customer disposition | AUTHORITATIVE | Technician field-evidence commands |
| Completion blockers and Invoice handoff | AUTHORITATIVE | Technician field state/handoff |
| Timekeeping and breaks | AUTHORITATIVE | Own Workday endpoints |
| Own Payroll statements | AUTHORITATIVE | Own Payroll projection; independent from field work |
| Customer contact action | SOURCE_REQUIRED | No assignment-safe Employee contact projection or intent command |
| Customer equipment/service history/warranty | AUTHORITATIVE | Job assignment + Branch + Asset permission projection; explicit Job↔Asset relationships only; history capped at 10 |
| Fleet, out-of-service, maintenance, custody | AUTHORITATIVE READ | Own-Employee custody and authorized-Branch projection; sensitive identifiers excluded |
| Technician inspection mutation | POLICY_REQUIRED | Readiness is visible; no accepted checklist/cadence/admission policy exists |
| Photos/documents | SOURCE_REQUIRED | No field artifact upload/custody contract |
| Estimate presentation | AUTHORITATIVE READ | Job assignment + Branch + Estimate permission + exact Job conversion/current issued revision |
| Estimate decision/delivery | SOURCE_REQUIRED | Mobile cannot rewrite a revision or originate a delivery/decision without a dedicated command |
| Customer signature | SOURCE_REQUIRED | No version-bound field authorization contract |
| Communications delivery status | PROVIDER_REQUIRED/SOURCE_REQUIRED | Communications owns recipient/template/provider; no field intent/status endpoint |
| Completed Job history | AUTHORITATIVE | Own-assignment/crew history, authorized Branch, 30-day/default and 90-day/50-record hard maximum |
| Employee notifications/push | SOURCE_REQUIRED/PROVIDER_REQUIRED | No Employee notification inbox/token-registration contract |
| Payment collection | POLICY_REQUIRED/SOURCE_REQUIRED | ACP Employee has no Technician collection authority |

## Offline and uncertainty contract

All field mutations are online-required. Arrival, lifecycle, evidence, Invoice handoff, and Timekeeping use idempotency or authoritative versioning and must reconcile after response uncertainty. Photos, Estimates, communications, and payments are unsupported offline. Cached data is explicitly last-confirmed/stale and cannot enable protected actions.

## Source contracts required

1. **Equipment:** delivered by assignment-scoped `GET /technician/jobs/{job_id}/equipment`; future source is needed only for upload/download of protected artifacts.
2. **Attachments:** initiate/upload-complete/read contracts bound to assigned Job/equipment, with size/MIME/content scanning, digest/idempotency, expiring protected URLs, EXIF policy, and orphan cleanup.
3. **Commercial:** assignment-scoped exact issued Estimate revision is delivered; separate present/deliver/decision commands remain required. No internal cost/margin is projected.
4. **Signature:** version-bound customer authorization record with signer disclosure, artifact custody, consent, and audit semantics.
5. **Communications:** field intent endpoint keyed to an operational transition; server resolves recipient, consent, template, channel and provider. An intent key must converge to one logical communication.
6. **Notifications:** own inbox plus provider-neutral device-token registration. Payload contains opaque target/reference only; every tap re-reads authorized state.
7. **History:** delivered by bounded own-assignment completed history with explicit range/limit.
8. **Fleet/custody:** own-Employee custody projection is delivered. Inspection execution still requires authoritative definition/cadence policy.
9. **Payments:** future Technician collection requires explicit permission, allowed tenders, amount/invoice authority, provider boundary, receipt, reversal/reconciliation, and offline prohibition.

## Attachment threat model

Reject oversized, unexpected or extension/MIME-mismatched content before upload; server repeats validation and malware/content inspection. Upload identity is server-issued, Job/Company/Branch bound, idempotent, digest checked, private by default, and inaccessible across Jobs or Companies. Protected URLs expire and are re-authorized. Mobile removes temporary content after confirmation/cancellation and strips location EXIF under accepted policy. Interrupted or response-lost upload reconciles by upload identity rather than creating another artifact.

## Notification and deep-link security

No notification payload grants authority. Job, Estimate, Invoice, or notification targets must contain only opaque identifiers and route hints. App launch restores session, refreshes authorization, re-fetches assignment-scoped data, and fails closed for reassignment, Branch/permission removal, deactivation, stale revisions, or foreign UUIDs. Lock-screen copy must exclude Customer details, addresses, financial values, access instructions, Payroll and notes.

## Expo 57 decision packet

The upgrade has already been completed and physically qualified in the accepted Mobile readiness lineage; this program reconciles it rather than initiating another major upgrade. It removes the previously reported high-severity dependency boundary and aligns Expo 57 with React Native 0.86 and React 19.2. Remaining advisories are moderate transitive dependencies without a compatible non-breaking fix. Impact included iOS 16.4 minimum deployment, native AppDelegate/MainApplication updates, Pods/Gradle/Metro reconciliation, Hermes exports, TypeScript 6, navigation/module alignment, and full Mobile regression. Rollback is the pre-upgrade Field Program commit lineage; do not partially downgrade packages. Expo 57 is recommended before Production and is now the qualified baseline.

## Acceptance rehearsals

### Physical iPhone V2

After protected integration and a safe synthetic assigned Job fixture: confirm Preview build identity; sign in; open My Day and Jobs; open Job Workspace; verify Customer/Location minimum fields; On My Way once; confirm state and communication status if available; Arrive; Start; record work summary/disposition; pause/resume; inspect exact completion blockers; Complete; refresh Invoice handoff; confirm Timekeeping remains independent; exercise permission revocation and recovery. Do not repeat punches merely for evidence.

### Synthetic technician day

Run all authoritative steps above against isolated synthetic records. At equipment, photo, Estimate, delivery, signature, notification, Fleet, and payment steps assert the exact SOURCE/POLICY/PROVIDER gate instead of simulating success.

### Failure day

For each mutation exercise pre-request network loss, response loss, 409, 502/503, session expiry, permission removal, Branch removal and app termination. Re-open and refresh server state before enabling another action. Upload interruption and stale Estimate revision remain contract simulations until their sources exist.

### Revocation and persona matrix

Restricted Employee sees only permission-derived My Day/My Time/Account. Technician sees assigned Jobs and only explicitly permitted actions. Multi-Branch authority shows assignments from granted Branches A/B and rejects C; revocation invalidates cached action authority on revalidation. A desktop administrator does not receive office, Accounting, Payroll administration, Migration or global reporting surfaces merely because those desktop permissions exist. Membership/Employee deactivation returns to safe authentication and clears protected visible state.

## Operational safety

Foreground and restored connectivity revalidate authority without background polling. Mutation controls block duplicate taps. Safe diagnostics contain route class, recovery class, request correlation, app version and Preview environment only. No password, token, Customer payload, provider error, Payroll value, or field note is logged. Privacy shield covers app-switcher snapshots. Maps are explicit external handoff; no location permission or tracking exists.

## Native gates

iOS Xcode 26.6/CocoaPods 1.17, Expo/Hermes, simulator, unsigned device and development-signed physical device builds are qualified. Distribution signing, live AASA, App Store Connect and TestFlight remain external. Android Hermes/configuration qualifies; JDK, Android SDK, device build, release signing, asset links and Play Console remain toolchain/external gates.

The Program 2 execution host currently selects Command Line Tools rather than full Xcode, has no `pod` executable, and has no Java runtime, so this increment can qualify Expo iOS/Android exports and committed native configuration but cannot repeat an Xcode/CocoaPods or Gradle build locally. The Info plist, privacy manifest, and entitlements parse successfully, including the expected associated domain. `expo-doctor` passes 19/21 checks: the two explicit gates are missing CocoaPods and native-project/app-config synchronization ownership. Because native folders are committed, future configuration changes must be reconciled in both native projects rather than assumed to flow from `app.json`.

The installed baseline is Expo 57.0.19, React Native 0.86.3, and React 19.2.3—not Expo 54. Production dependency audit reports 17 moderate transitive advisories and no high or critical advisories. The package manager proposes an invalid major downgrade as its aggregate automatic fix, so no forced audit fix or major framework change is accepted here. A future upgrade must use the Expo-supported target at that time, regenerate/reconcile native projects in an isolated lane, preserve SecureStore/linking/Hermes/navigation behavior, run both platform builds, repeat the full synthetic device packet, and retain the current branch/build as rollback. TestFlight remains downstream of owner-authorized signing.

## Program 2 physical-iPhone acceptance packet

Use only the synthetic Preview technician and synthetic assigned records. Refresh before each mutation; if the app says stale, unavailable, or needs confirmation, do not retry until the authoritative state is visible.

1. Open **My Day**, open its assigned Job, and confirm only that Job's equipment appears. Expected server evidence: successful assignment-scoped equipment read. A foreign Job/Asset URL must present unavailable without existence disclosure. Read-only retry is safe.
2. Confirm manufacturer/model when recorded, installation evidence, warranty evidence wording, and a maximum of ten service-history records per asset. “Evidence unavailable” must never be phrased as warranty coverage. Read-only retry is safe.
3. Review **My field readiness**. Only the synthetic Employee's custody Fleet/Tool records may appear. Out-of-service must be text, not color alone. Inspection remains `POLICY_REQUIRED`; no inspection tap is expected.
4. Review **Estimate**. Only a current issued revision explicitly converted to this assigned Job may appear, with line presentation and total. No edit, acceptance, or arbitrary delivery control may appear. Read-only retry is safe.
5. Open **Jobs → Completed/recent**. Confirm the 30-day, 20-record bounded own-assignment history and no Company-wide history. Read-only retry is safe.
6. Disable connectivity after a successful context refresh. Confirm `LAST CONFIRMED — STALE`, retained read-only context, and no new field-context mutation. Restore connectivity and pull to refresh; reinstall must not be required.
7. Remove Asset or Estimate permission from a separate synthetic control session, foreground the app, and confirm that surface disappears or returns permission changed. Direct API access must deny. Restore authority and reauthenticate/refresh as directed by the server.
8. Revoke the synthetic Branch or assignment and open a previously known deep link. The Job and all related equipment/Estimate context must become unavailable without revealing existence.

External/provider-gated: notification inbox, push admission/delivery, communications delivery proof, attachment upload/download, and inspection execution. Apple-gated: distribution signing, App Store Connect, and TestFlight. None is part of this safe Preview sequence.
