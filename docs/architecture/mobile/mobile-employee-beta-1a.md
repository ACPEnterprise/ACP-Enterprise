# ACP Employee beta distribution contract

MOBILE.EMPLOYEE.BETA.1A prepares the application for signed-device beta builds. It does not create signing credentials, external store records, association files, or a deployment.

## Build identity and environments

- Product/display name: `ACP Employee`.
- iOS bundle identifier and Android application ID: `com.acpenterprise.employee`.
- Marketing version uses SemVer and begins at `0.1.0`. Every distributed artifact receives a monotonically increasing iOS `CFBundleVersion`/build number and Android `versionCode`; Expo and checked-in native metadata must remain aligned.
- The `beta` distribution profile is a store-signed profile whose runtime environment is Preview. It is pinned to `https://preview.allcountyhomeservices.com`.
- Production is deliberately unconfigured and fails closed unless both a real HTTPS endpoint and `EXPO_PUBLIC_PRODUCTION_ACTIVATED=true` are supplied by a separately approved release process.
- No secrets, signing material, or credentials belong in EAS configuration or source control.

## Apple application-side contract

The future Apple App ID must use `com.acpenterprise.employee` and enable Associated Domains. The app entitlement is `applinks:employee.acpenterprise.com`. The ACP-controlled host must eventually serve, over HTTPS without a redirect:

`https://employee.acpenterprise.com/.well-known/apple-app-site-association`

```json
{
  "applinks": {
    "details": [
      {
        "appIDs": ["<APPLE_TEAM_ID>.com.acpenterprise.employee"],
        "components": [
          { "/": "/activate", "comment": "ACP employee activation" },
          { "/": "/activate/*", "comment": "ACP employee activation variants" }
        ]
      }
    ]
  }
}
```

Serve this as `application/json`. The invitation secret remains a transient query value handled by the activation route; it must not appear in the association document, logs, analytics, or ordinary persistence.

External Apple gates are full Xcode and CocoaPods, an Apple Developer team, an explicit App ID/capability registration, distribution certificate and provisioning profile, an App Store Connect app record, signed archive validation, TestFlight upload authorization, and physical-device beta testing. No Apple resource was created here.

## Android application-side contract

The Android App Link is `https://employee.acpenterprise.com/activate` (including child paths). The same ACP-controlled host must eventually serve:

`https://employee.acpenterprise.com/.well-known/assetlinks.json`

```json
[
  {
    "relation": ["delegate_permission/common.handle_all_urls"],
    "target": {
      "namespace": "android_app",
      "package_name": "com.acpenterprise.employee",
      "sha256_cert_fingerprints": ["<ANDROID_APP_SIGNING_CERT_SHA256>"]
    }
  }
]
```

External Android gates are a supported JDK and Android SDK, release keystore or Play App Signing enrollment, verified release bundle, Play Console application/internal-test track, and emulator/physical-device testing. No Google resource or signing key was created here.

## Device security posture

Session material remains behind the SecureStore abstraction (iOS Keychain and Android encrypted storage), and Android backup rules exclude SecureStore records. Passwords and invitation secrets are not persisted. Logout revokes the server session when available and purges protected local session state and authenticated navigation state. Release transport requires HTTPS; only development manifests permit local cleartext traffic. The application adds a task-switcher privacy shield while inactive. Active-screen capture remains an operating-system/user capability and should be reassessed if a later product requirement introduces unusually sensitive employee-visible content. No analytics or employee/device tracking vendor is present.

## First signed-beta acceptance flow

Using a synthetic Preview identity only:

1. Install and open ACP Employee.
2. Activate from a protected invitation link or sign in.
3. Confirm authoritative Membership/Employee resolution and capabilities.
4. Clock In, Start Break, End Break, and Clock Out; confirm each server-authoritative response and idempotent recovery behavior.
5. Open My Time and confirm authoritative evidence.
6. Log out, verify protected state is cleared, and sign in again.
7. Interrupt network connectivity, verify no punch success is fabricated, restore connectivity, and confirm authoritative reconciliation.

My Day and read-only assignment detail may be exercised but are not release blockers for the first Timeclock/My Time beta. Publishing or provisioning real employees requires separate owner approval.
