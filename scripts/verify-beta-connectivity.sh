#!/bin/sh
set -eu

preview_url=https://preview.allcountyhomeservices.com
beta_url=https://beta.twelve-hats.com
expected_beta_ipv4=${EXPECTED_BETA_IPV4:-162.243.234.193}

temporary_headers=$(mktemp)
temporary_body=$(mktemp)
preview_health=$(mktemp)
beta_health=$(mktemp)
trap 'rm -f "$temporary_headers" "$temporary_body" "$preview_health" "$beta_health"' EXIT HUP INT TERM

require_status() {
  expected=$1
  url=$2
  actual=$(curl --silent --show-error --max-time 15 --output /dev/null --write-out '%{http_code}' "$url")
  if [ "$actual" != "$expected" ]; then
    echo "Unexpected status for $url: expected $expected, received $actual" >&2
    exit 1
  fi
}

require_single_header() {
  header_name=$1
  header_count=$(grep -ic "^${header_name}:" "$temporary_headers" || true)
  if [ "$header_count" != "1" ]; then
    echo "Expected exactly one $header_name header; received $header_count" >&2
    exit 1
  fi
}

require_header_value() {
  header_name=$1
  expected=$2
  if ! grep -Eiq "^${header_name}:[[:space:]]*${expected}[[:space:]]*\r?$" "$temporary_headers"; then
    echo "Missing or unsafe $header_name response header." >&2
    exit 1
  fi
}

require_https_redirect() {
  hostname=$1
  curl --silent --show-error --max-time 15 --head "http://$hostname/" >"$temporary_headers"
  grep -Eq '^HTTP/[0-9.]+ 30[178]([[:space:]]|$)' "$temporary_headers"
  grep -iq "^location: https://$hostname/" "$temporary_headers"
}

beta_ipv4=$(dig +short A beta.twelve-hats.com | sort -u)
if [ "$beta_ipv4" != "$expected_beta_ipv4" ]; then
  echo "beta.twelve-hats.com must resolve only to $expected_beta_ipv4; observed: ${beta_ipv4:-UNRESOLVED}" >&2
  exit 1
fi

for base_url in "$preview_url" "$beta_url"; do
  require_status 200 "$base_url/"
  require_status 200 "$base_url/healthz"
  require_status 200 "$base_url/backend-health"
  require_status 200 "$base_url/employees"
  require_status 401 "$base_url/api/v1/auth/session"
  curl --silent --show-error --max-time 15 --head "$base_url/" >"$temporary_headers"
  require_single_header strict-transport-security
  require_single_header content-security-policy
  require_single_header x-content-type-options
  require_single_header x-frame-options
  require_single_header referrer-policy
  require_single_header permissions-policy
  require_header_value strict-transport-security 'max-age=(31536000|[4-9][0-9]{7,}|[1-9][0-9]{8,});[[:space:]]*includeSubDomains'
  require_header_value x-content-type-options nosniff
  require_header_value x-frame-options DENY
  require_header_value referrer-policy no-referrer
  require_header_value permissions-policy '.+'
  require_header_value content-security-policy '.+'
done

require_https_redirect preview.allcountyhomeservices.com
require_https_redirect beta.twelve-hats.com

curl --fail --silent --show-error --max-time 15 "$preview_url/backend-health" >"$preview_health"
curl --fail --silent --show-error --max-time 15 "$beta_url/backend-health" >"$beta_health"
if ! cmp -s "$preview_health" "$beta_health"; then
  echo "Preview and Beta backend health projections differ." >&2
  exit 1
fi

require_status 404 "$beta_url/mission-control"
require_status 404 "$beta_url/engineering"
require_status 404 "$beta_url/api/v1/worker-transport/sessions/challenge"

cors_headers=$(curl --silent --show-error --max-time 15 --request OPTIONS \
  --header 'Origin: https://beta.twelve-hats.com' \
  --header 'Access-Control-Request-Method: POST' \
  --dump-header - --output /dev/null \
  "$beta_url/api/v1/auth/login")
printf '%s\n' "$cors_headers" | grep -iq '^access-control-allow-origin: https://beta.twelve-hats.com'
printf '%s\n' "$cors_headers" | grep -iq '^access-control-allow-credentials: true'

untrusted_cors_status=$(curl --silent --show-error --max-time 15 --request OPTIONS \
  --header 'Origin: https://untrusted.invalid' \
  --header 'Access-Control-Request-Method: POST' \
  --dump-header "$temporary_headers" --output "$temporary_body" \
  --write-out '%{http_code}' \
  "$beta_url/api/v1/auth/login")
if [ "$untrusted_cors_status" != "400" ]; then
  echo "Untrusted Beta CORS origin returned HTTP $untrusted_cors_status instead of 400." >&2
  exit 1
fi
if grep -iq '^access-control-allow-origin:' "$temporary_headers"; then
  echo "Untrusted Beta CORS origin received an allow-origin header." >&2
  exit 1
fi

if [ "${REQUIRE_PUBLIC_METADATA:-0}" = "1" ]; then
  curl --fail --silent --show-error --max-time 15 "$beta_url/" >"$temporary_body"
  root_digest=$(openssl dgst -sha256 "$temporary_body")
  for public_path in support privacy; do
    curl --fail --silent --show-error --max-time 15 "$beta_url/$public_path" >"$temporary_body"
    if [ "$(openssl dgst -sha256 "$temporary_body")" = "$root_digest" ]; then
      echo "$beta_url/$public_path still resolves to the generic application shell." >&2
      exit 1
    fi
  done
fi

certificate_file=$(mktemp)
trap 'rm -f "$temporary_headers" "$temporary_body" "$preview_health" "$beta_health" "$certificate_file"' EXIT HUP INT TERM
echo | openssl s_client -servername beta.twelve-hats.com \
  -connect beta.twelve-hats.com:443 2>/dev/null \
  | openssl x509 >"$certificate_file"
certificate_expiry=$(openssl x509 -in "$certificate_file" -noout -enddate | cut -d= -f2-)
test -n "$certificate_expiry"
if ! openssl x509 -in "$certificate_file" -noout -checkend 1209600; then
  echo "Beta TLS certificate expires in less than 14 days." >&2
  exit 1
fi

echo "Preview and Twelve Hats Beta connectivity accepted."
echo "beta_ipv4=$beta_ipv4"
echo "beta_certificate_expiry=$certificate_expiry"
