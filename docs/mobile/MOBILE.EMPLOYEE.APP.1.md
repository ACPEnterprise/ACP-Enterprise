# MOBILE.EMPLOYEE.APP.1 — Native Employee Application Foundation

## Decision

ACP Employee uses React Native with Expo (managed/prebuild) and TypeScript. This follows ACP's React, TypeScript, npm, lint, and test conventions while retaining one commercial iOS/Android application. Expo configuration is native-project input, not a second backend. `expo prebuild` can produce ordinary Xcode and Gradle projects when native customization or store delivery requires them.

Alternatives inspected: separate Swift/Kotlin applications (maximum platform control but duplicated presentation and two specialist toolchains); Flutter (maintainable cross-platform option but introduces Dart and does not reuse ACP's TypeScript/React knowledge); bare React Native (compatible but carries generated native projects and upgrades before APP.1 needs divergence). Expo was selected for repeatable native configuration, protected storage, linking, connectivity, development builds, and straightforward future EAS or local builds.

## Boundaries

`mobile/` is an independent client. ACP Enterprise remains authoritative for identity, membership, Employee linkage, Company/Branch, authorization, timekeeping, timestamps, timezone, and evidence. There is no mobile database, business-rule engine, PIN identity, employee-number login, HCP identity, Payroll, or compensation feature.

The current server contracts inspected were `/api/v1/auth/login`, `/refresh`, `/logout`, protected identity onboarding `/api/v1/identity-onboarding/activate/complete`, and read-only `/api/v1/timekeeping/me/state` and `/timecard`. APP.1 establishes typed centralized transport and route boundaries without issuing invitations or performing time mutations.

## Architecture

- Environments are explicit development, preview, and production values. Zod validation fails closed. Preview and production example URLs are deliberately invalid placeholders; production updates are disabled and production is not activated.
- Session secrets are persisted only through `ProtectedStorage`, implemented with iOS Keychain/Android Keystore-backed Expo SecureStore using device-only accessibility. Passwords are never stored. Malformed/stale sessions clear safely; logout and 401 handling clear protected state.
- `ApiClient` centralizes authenticated headers, timeout, connectivity, 401 expiration, 403 denial, server failure, and schema validation. Screens do not call HTTP. Server failures never become local successes.
- Navigation separates anonymous and authenticated stacks. Bottom tabs initially expose Home and permission-gated My Time. Future destinations are represented as capabilities but are not implemented.
- Home contains no runtime fixture business data. My Time states server authority and provides the native contract boundary only.
- iOS Universal Links and Android verified App Links use `https://employee.acpenterprise.com/activate`; `acpemployee://` is development fallback. Invitation secrets must be passed directly to protected activation handling, never logs, analytics, crash context, ordinary navigation params, or tests.
- NetInfo provides reusable explicit online/offline state. Offline requests fail before transport; no optimistic mutation queue or competing business database exists.
- Version `0.1.0`, native build numbers (assigned by build infrastructure), Expo runtime version, and `X-ACP-Mobile-Version` establish the compatibility boundary. Forced update is intentionally deferred.
- Diagnostics use a redacting logger and no third-party analytics/tracking vendor.

## Native implications and external gates

iOS configuration defines `com.acpenterprise.employee`, phone orientation, Keychain-backed storage, and Associated Domains. Local simulator compilation needs compatible Xcode/CocoaPods; device/TestFlight/App Store delivery later needs Apple Developer team membership, certificates/profiles, registered bundle ID/Associated Domains, App Store Connect record, privacy metadata, and hosted `apple-app-site-association`.

Android configuration defines `com.acpenterprise.employee`, Keystore-backed storage, and verified intent filters. Local native compilation needs a compatible JDK and Android SDK. Device/internal/Play delivery later needs upload/app-signing keys, Play Console application, store/privacy metadata, and hosted `assetlinks.json` containing the release signing certificate fingerprint.

## Dependencies

Expo/React Native provide the shared native runtime; React Navigation provides expandable native navigation; SecureStore provides protected secret storage; NetInfo provides connectivity state; Expo Linking/Constants provide native links and build configuration; Zod validates environment and response boundaries. Jest Expo, Testing Library, TypeScript, ESLint, and TSX provide qualification tooling. No unrelated repository package is upgraded.
