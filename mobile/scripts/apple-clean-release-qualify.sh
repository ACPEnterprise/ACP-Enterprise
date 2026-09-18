#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."

if ! git diff --quiet -- package.json package-lock.json ios/Podfile ios/Podfile.lock; then
  echo "Dependency inputs must be clean before deterministic release qualification" >&2
  exit 1
fi

npm ci
(cd ios && pod install --deployment)
npm test -- --runInBand
npm run typecheck
npm run lint
npm run config:validate
npm run apple:archive:qualify

echo "Clean dependency install and unsigned Preview Release archive qualified. Signing and upload were not performed."
