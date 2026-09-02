#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."
npm run apple:preflight
npm run config:validate

archive_path="$PWD/build/apple/ACPEmployee-preview-unsigned.xcarchive"
build_log="$PWD/build/apple/archive-build.log"
rm -rf "$archive_path"
EXPO_PUBLIC_APP_ENV=preview EXPO_PUBLIC_API_BASE_URL=https://preview.allcountyhomeservices.com \
  xcodebuild archive -workspace ios/ACPEmployee.xcworkspace -scheme ACPEmployee -configuration Release \
  -destination 'generic/platform=iOS' -archivePath "$archive_path" \
  CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO >"$build_log" 2>&1 || { tail -80 "$build_log"; exit 1; }
tail -20 "$build_log"

app="$archive_path/Products/Applications/ACPEmployee.app"
test -d "$app"
test "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$app/Info.plist")" = "com.acpenterprise.employee"
test "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$app/Info.plist")" = "0.2.0"
test "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$app/Info.plist")" = "2"
bundle_strings="$PWD/build/apple/bundle-strings.txt"
strings "$app/main.jsbundle" >"$bundle_strings"
grep -q 'https://preview.allcountyhomeservices.com' "$bundle_strings"
if grep -Eq 'production-api\.example\.invalid|http://localhost:8000' "$bundle_strings"; then
  echo "Unsigned archive contains a prohibited non-Preview endpoint" >&2
  exit 1
fi
if codesign -d "$app" >/dev/null 2>&1; then
  echo "Unsigned archive unexpectedly contains signing material" >&2
  exit 1
fi
echo "Unsigned Preview xcarchive qualified. It is not distributable and was not uploaded."
