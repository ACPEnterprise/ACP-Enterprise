#!/bin/sh
set -eu

preview_url="${PREVIEW_URL:-https://preview.allcountyhomeservices.com}"
html_file="$(mktemp)"
root_html_file="$(mktemp)"
body_file="$(mktemp)"
enterprise_contract="$(mktemp)"
mission_contract="$(mktemp)"
trap 'find "$html_file" "$root_html_file" "$body_file" "$enterprise_contract" "$mission_contract" -delete' EXIT HUP INT TERM

curl --fail --silent --show-error "$preview_url/engineering" > "$html_file"
curl --fail --silent --show-error "$preview_url/mission-control" > "$root_html_file"
asset_path="$(sed -n 's/.*src="\([^\"]*index-[^\"]*\.js\)".*/\1/p' "$html_file" | head -1)"
case "$asset_path" in
  /mission-assets/*) ;;
  *) echo "Engineering HTML does not own a /mission-assets/ bundle." >&2; exit 1 ;;
esac
root_asset_path="$(sed -n 's/.*src="\([^\"]*index-[^\"]*\.js\)".*/\1/p' "$root_html_file" | head -1)"
if [ "$root_asset_path" != "$asset_path" ]; then
  echo "Mission Control root and deep link do not resolve to one artifact." >&2
  exit 1
fi
asset_type="$(curl --fail --silent --show-error --output /dev/null \
  --write-out '%{content_type}' "$preview_url$asset_path")"
case "$asset_type" in
  application/javascript*|text/javascript*) ;;
  *) echo "Mission Control bundle returned unexpected content type $asset_type." >&2; exit 1 ;;
esac

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

curl --fail --silent --show-error \
  "$preview_url/api/v1/platform/contracts" > "$enterprise_contract"
curl --fail --silent --show-error \
  "$preview_url/api/v1/engineering/platform-contracts" > "$mission_contract"
if ! cmp -s "$enterprise_contract" "$mission_contract"; then
  echo "Enterprise and Mission Control platform contracts have drifted." >&2
  exit 1
fi

echo "mission_control_html=healthy"
echo "mission_control_assets=healthy"
echo "mission_control_proxy=trusted"
echo "mission_control_authentication=fail_closed"
echo "platform_contracts=consistent"
