#!/bin/sh
set -eu

preview_url="${PREVIEW_URL:-https://preview.allcountyhomeservices.com}"
html_file="$(mktemp)"
body_file="$(mktemp)"
trap 'find "$html_file" "$body_file" -delete' EXIT HUP INT TERM

curl --fail --silent --show-error "$preview_url/engineering" > "$html_file"
asset_path="$(sed -n 's/.*src="\([^\"]*index-[^\"]*\.js\)".*/\1/p' "$html_file" | head -1)"
case "$asset_path" in
  /mission-assets/*) ;;
  *) echo "Engineering HTML does not own a /mission-assets/ bundle." >&2; exit 1 ;;
esac
curl --fail --silent --show-error --output /dev/null "$preview_url$asset_path"

status="$(curl --silent --show-error --output "$body_file" --write-out '%{http_code}' \
  "$preview_url/api/v1/engineering/mobile/roadmaps")"
if [ "$status" != "401" ]; then
  echo "Mission Control proxy rejected the API availability probe with HTTP $status." >&2
  sed -n '1p' "$body_file" >&2
  exit 1
fi
if ! grep -q 'Authentication required' "$body_file"; then
  echo "Mission Control API did not fail closed with its authentication contract." >&2
  exit 1
fi

echo "mission_control_html=healthy"
echo "mission_control_assets=healthy"
echo "mission_control_proxy=trusted"
echo "mission_control_authentication=fail_closed"
