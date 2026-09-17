#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

command -v node >/dev/null || { echo "Node.js is required; install the repository-supported Node version." >&2; exit 1; }
command -v npm >/dev/null || { echo "npm is required." >&2; exit 1; }
command -v pod >/dev/null || { echo "CocoaPods is required; install it through the approved Homebrew environment." >&2; exit 1; }

test -d node_modules || npm ci --ignore-scripts
npm run typecheck
npm run lint
npm run config:validate
(cd ios && pod install --deployment --no-repo-update)
test -f ios/Pods/Target\ Support\ Files/Pods-ACPEmployee/Pods-ACPEmployee.release.xcconfig || {
  echo "Pods-ACPEmployee.release.xcconfig is missing. Run pod install from mobile/ios and inspect Podfile/lockfile." >&2
  exit 1
}

xcode-select -p | grep -q '/Applications/Xcode.app/Contents/Developer' || {
  echo "Full Xcode is not selected. Select it with: sudo xcode-select --switch /Applications/Xcode.app/Contents/Developer" >&2
  exit 1
}
xcodebuild -workspace ios/ACPEmployee.xcworkspace -scheme ACPEmployee -configuration Release -sdk iphonesimulator \
  -derivedDataPath /tmp/acp-employee-release-derived CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO build
