#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."
npm run apple:preflight

archive_path="$PWD/build/apple/ACPEmployee-preview-unsigned.xcarchive"
build_log="$PWD/build/apple/archive-build.log"
mkdir -p "$(dirname "$archive_path")"
rm -rf "$archive_path"
EXPO_PUBLIC_APP_ENV=preview EXPO_PUBLIC_API_BASE_URL=https://preview.allcountyhomeservices.com \
  xcodebuild archive -workspace ios/ACPEmployee.xcworkspace -scheme ACPEmployee -configuration Release \
  -destination 'generic/platform=iOS' -archivePath "$archive_path" \
  CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO >"$build_log" 2>&1 || { tail -80 "$build_log"; exit 1; }

app="$archive_path/Products/Applications/ACPEmployee.app"
expected_version="$(node -p "require('./app.json').expo.version")"
expected_build="$(node -p "require('./app.json').expo.ios.buildNumber")"
test -d "$app"
test "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$app/Info.plist")" = "com.acpenterprise.employee"
test "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$app/Info.plist")" = "$expected_version"
test "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$app/Info.plist")" = "$expected_build"
if codesign -d "$app" >/dev/null 2>&1; then
  echo "Unsigned archive unexpectedly contains signing material" >&2
  exit 1
fi
echo "Unsigned Preview xcarchive qualified. It is not distributable and was not uploaded."
