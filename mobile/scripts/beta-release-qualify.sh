#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."
npm ci
npm run beta:preflight
EXPO_PUBLIC_APP_ENV=preview EXPO_PUBLIC_API_BASE_URL=https://preview.allcountyhomeservices.com \
  npx expo export --platform all --output-dir build/beta/export

if command -v pod >/dev/null 2>&1; then
  (cd ios && pod install)
else
  echo "CocoaPods is required for iOS native qualification" >&2
  exit 1
fi

if xcode-select -p | grep -q '/Applications/Xcode.app/Contents/Developer'; then
  EXPO_PUBLIC_APP_ENV=preview EXPO_PUBLIC_API_BASE_URL=https://preview.allcountyhomeservices.com \
    xcodebuild -workspace ios/ACPEmployee.xcworkspace -scheme ACPEmployee -configuration Release \
    -destination 'generic/platform=iOS' -derivedDataPath ios/build/BetaOperationsDerivedData \
    CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO build
else
  echo "Full Xcode is not selected; Hermes exports passed but native iOS qualification is externally gated" >&2
  exit 2
fi

echo "Unsigned ACP Employee Preview beta qualification passed; signing and upload were not attempted."
